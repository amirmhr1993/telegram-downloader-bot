import os
import re
import tempfile
import subprocess
import json
import yt_dlp


COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt")


class YouTubeDownloader:
    QUALITY_MAP = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
    }

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        pattern = r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?.*v=|shorts/)|youtu\.be/)"
        return bool(re.match(pattern, url))

    @staticmethod
    def _base_cmd():
        cmd = ["python", "-m", "yt_dlp", "--js-runtimes", "node", "--no-warnings"]
        if os.path.exists(COOKIES_FILE):
            cmd += ["--cookies", COOKIES_FILE]
        return cmd

    @staticmethod
    async def get_formats(url: str) -> dict:
        cmd = YouTubeDownloader._base_cmd() + [
            "--skip-download", "--dump-json", url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            raise Exception(result.stderr.strip() or "Failed to get video info")

        info = json.loads(result.stdout)
        formats = []
        seen_heights = set()
        for f in info.get("formats", []):
            height = f.get("height")
            if height and height not in seen_heights and f.get("ext") == "mp4":
                seen_heights.add(height)
                formats.append({"height": height, "label": f"{height}p"})

        formats.sort(key=lambda x: x["height"], reverse=True)
        if not formats:
            formats = [{"height": None, "label": "Best available"}]

        title = info.get("title", "video")
        return {"title": title, "formats": formats}

    @staticmethod
    async def download(url: str, quality: str, progress_callback=None) -> str:
        tmp_dir = tempfile.mkdtemp()
        output_path = os.path.join(tmp_dir, "%(title)s.%(ext)s")

        format_str = YouTubeDownloader.QUALITY_MAP.get(quality, YouTubeDownloader.QUALITY_MAP["best"])

        cmd = YouTubeDownloader._base_cmd() + [
            "-f", format_str,
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--newline",
            url,
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        for line in proc.stdout:
            line = line.strip()
            if progress_callback and "%" in line:
                try:
                    parts = line.split()
                    for part in parts:
                        if "%" in part:
                            pct = float(part.replace("%", ""))
                            speed = "N/A"
                            if "/" in line:
                                speed_part = line.split("/")[-1].strip().split()[0] if line.split("/")[-1].strip() else "N/A"
                                speed = speed_part
                            progress_callback(pct, speed)
                            break
                except (ValueError, IndexError):
                    pass

        proc.wait()

        if proc.returncode != 0:
            raise Exception("Download failed")

        # Find the downloaded file
        for f in os.listdir(tmp_dir):
            if f.endswith(".mp4") or f.endswith(".webm") or f.endswith(".mkv"):
                filepath = os.path.join(tmp_dir, f)
                # Convert to mp4 if needed
                if not f.endswith(".mp4"):
                    mp4_path = filepath.rsplit(".", 1)[0] + ".mp4"
                    convert_cmd = ["ffmpeg", "-i", filepath, "-c", "copy", mp4_path, "-y"]
                    subprocess.run(convert_cmd, capture_output=True, timeout=120)
                    if os.path.exists(mp4_path):
                        os.remove(filepath)
                        filepath = mp4_path
                return filepath

        raise Exception("No output file found")
