import os
import re
import tempfile
import instaloader


class InstagramDownloader:
    @staticmethod
    def is_instagram_url(url: str) -> bool:
        pattern = r"(?:https?://)?(?:www\.)?(?:instagram\.com/(?:p/|reel/|tv/)|instagr\.am/)"
        return bool(re.match(pattern, url))

    @staticmethod
    def _extract_shortcode(url: str) -> str | None:
        """Extract shortcode from Instagram URL."""
        pattern = r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    @staticmethod
    async def download(url: str, progress_callback=None) -> list[str]:
        """Download Instagram post/reel and return list of file paths."""
        shortcode = InstagramDownloader._extract_shortcode(url)
        if not shortcode:
            raise ValueError("Could not extract shortcode from URL")

        if progress_callback:
            progress_callback(10, "Fetching post info...")

        L = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            dirname_pattern="{tmp_dir}",
            filename_pattern="{date_utc:%Y%m%d_%H%M%S}_{shortcode}",
        )

        tmp_dir = tempfile.mkdtemp()
        L.dirname_pattern = tmp_dir

        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
        except Exception as e:
            raise ValueError(f"Could not fetch post: {e}. The post may be private or the URL may be invalid.")

        if progress_callback:
            progress_callback(40, "Downloading media...")

        files = []

        if post.typename == "GraphVideo" or post.typename == "Reel":
            L.download_post(post, target=tmp_dir)
            for f in os.listdir(tmp_dir):
                if f.endswith(".mp4"):
                    files.append(os.path.join(tmp_dir, f))
        elif post.typename == "GraphSidecar":
            L.download_post(post, target=tmp_dir)
            for f in os.listdir(tmp_dir):
                if f.endswith((".mp4", ".jpg", ".png", ".webp")):
                    files.append(os.path.join(tmp_dir, f))
        else:
            L.download_post(post, target=tmp_dir)
            for f in os.listdir(tmp_dir):
                if f.endswith((".jpg", ".png", ".webp", ".mp4")):
                    files.append(os.path.join(tmp_dir, f))

        if progress_callback:
            progress_callback(100, "Upload ready")

        if not files:
            raise ValueError("No media files found in the post")

        return files
