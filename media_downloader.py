import time
from pathlib import Path
import asyncio
import os

from open_gopro import WiredGoPro, Params
from open_gopro.models import MediaItem
import requests.exceptions


class MediaDownloader():
    def __init__(self, gopro: WiredGoPro, dest_dir: Path):
        self.gopro = gopro
        self.download_dest = dest_dir
        self.last_downloaded_file = Path('.download') / '.last-downloaded.txt'

    def get_last_downloaded_filename(self) -> str:
        last_downloaded = self.last_downloaded_file.read_text() if self.last_downloaded_file.exists() else ''
        return Path(last_downloaded).name

    async def get_media_list_from_camera(self) -> list[MediaItem]:
        media_list = await self.gopro.http_command.get_media_list()
        all_files = media_list.data.files
        all_files.sort(key = lambda media_item: media_item.filename)

        return all_files

    async def download_all_new(self):
        all_files = await self.get_media_list_from_camera()

        last_downloaded = self.get_last_downloaded_filename()
        file_list = [file for file in all_files if Path(file.filename).name > last_downloaded]

        print(f"Downloading latest {len(file_list)} of {len(all_files)} on camera.")
        await self.gopro.http_command.set_turbo_mode(mode=Params.Toggle.ENABLE)

        for media_item in file_list:
            await self.download_file(media_item.filename)

        await self.gopro.http_command.set_turbo_mode(mode=Params.Toggle.DISABLE)

    async def download_file(self, filename: str):
        local_file = self.download_dest / Path(filename).name
        if local_file.exists():
            return

        # if media_item.filename not in files_to_download:
        #     continue
        file_meta = (await self.gopro.http_command.get_media_metadata(path=filename)).data
        # print(file_meta)
        file_timestamp = int(file_meta.creation_timestamp)
        file_size = int(file_meta.file_size)
        print(f"Downloading {filename} ({file_size} bytes)")

        for tries in range(1000):
            try:
                start_time = time.time()
                await self.gopro.http_command.download_file(camera_file=filename, local_file=local_file)
                elapsed = time.time() - start_time
                throughput = file_size / 1048576 / elapsed
                print(f'Download complete in {elapsed}s {throughput} MiB/s')
                os.utime(local_file, (file_timestamp, file_timestamp))
                self.last_downloaded_file.write_text(filename)
                return
            except requests.exceptions.ConnectionError as e:
                print(f'[Retrying {tries}]')
                # TODO : Need to delete a failed file.
                await asyncio.sleep(2)
