import os
import re
import tempfile
import yt_dlp


COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")


class YouTubeDownloader:
    QUALITY_MAP = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
    }

    @staticmethod
    def _get_base_opts():
        opts = {"quiet": True, "no_warnings": True}
        if os.path.exists(COOKIES_FILE):
            opts["cookies"] = COOKIES_FILE
        return opts

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        pattern = r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?.*v=|shorts/)|youtu\.be/)"
        return bool(re.match(pattern, url))

    @staticmethod
    async def get_formats(url: str) -> list[dict]:
        ydl_opts = YouTubeDownloader._get_base_opts()
        ydl_opts["skip_download"] = True

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

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

        def progress_hook(d):
            if progress_callback and d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    percent = downloaded / total * 100
                    speed = d.get("speed")
                    speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "N/A"
                    progress_callback(percent, speed_str)
            elif progress_callback and d["status"] == "finished":
                progress_callback(100, "Processing...")

        ydl_opts = YouTubeDownloader._get_base_opts()
        ydl_opts.update({
            "format": format_str,
            "outtmpl": output_path,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if not filename.endswith(".mp4"):
            mp4_path = filename.rsplit(".", 1)[0] + ".mp4"
            if os.path.exists(mp4_path):
                filename = mp4_path

        return filename
