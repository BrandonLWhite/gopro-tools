import asyncio
import re
import sys
import asyncio
import argparse
import os
from typing import Any
from pathlib import Path
import time

from bleak import BleakScanner, BleakClient, AdvertisementData
from bleak.backends.device import BLEDevice as BleakDevice
import requests.exceptions

from open_gopro import WirelessGoPro, WiredGoPro, Params

# File deletion is possible but not currently part of the SDK: https://github.com/gopro/OpenGoPro/issues/74
#   Will take a little extending to get it working, but seems doable.
async def main() -> None:
    await test_wired()
    # await test_wireless()


async def test_wired() -> None:
    """
    Xfer rate is all over the place.  12-41 MiB/s in one case!
    Actually, it really seems to stay fast after the first few files.
    So, wired/USB is the way to go here.  As good as it gets.  WiFi is slower.
    """
    files_to_download = set((f"100GOPRO/GX0{index}.MP4" for index in range (12481, 12508)))

    download_dest = Path(".download")
    last_downloaded_file = download_dest / '.last-downloaded.txt'
    last_downloaded = last_downloaded_file.read_text() if last_downloaded_file.exists() else ''

    async with WiredGoPro() as gopro:
        cam_info = await gopro.http_command.get_camera_info()
        print(cam_info)
        media_list = await gopro.http_command.get_media_list()
        all_files = media_list.data.files
        all_files.sort(key = lambda media_item: media_item.filename)
        file_list = [file for file in all_files if file.filename > last_downloaded]

        print(f"Downloading latest {len(file_list)} of {len(all_files)} on camera.")
        await gopro.http_command.set_turbo_mode(mode=Params.Toggle.ENABLE)

        for media_item in file_list:
            local_file = download_dest / Path(media_item.filename).name
            if local_file.exists():
                continue
            print(media_item.filename)
            # if media_item.filename not in files_to_download:
            #     continue
            file_meta = (await gopro.http_command.get_media_metadata(path=media_item.filename)).data
            print(file_meta)
            file_timestamp = int(file_meta.creation_timestamp)
            file_size = int(file_meta.file_size)
            print(f"Downloading {media_item.filename} ({file_size} bytes)")

            for tries in range(10):
                try:
                    start_time = time.time()
                    await gopro.http_command.download_file(camera_file=media_item.filename, local_file=local_file)
                    elapsed = time.time() - start_time
                    throughput = file_size / 1048576 / elapsed
                    print(f'Download complete in {elapsed}s {throughput} MiB/s')
                    os.utime(local_file, (file_timestamp, file_timestamp))
                    last_downloaded_file.write_text(media_item.filename)
                    break
                except requests.exceptions.ConnectionError as e:
                    print(f'[Retrying {tries}]')
                    # TODO : Need to delete a failed file.
                    await asyncio.sleep(2)

        await gopro.http_command.set_turbo_mode(mode=Params.Toggle.DISABLE)

async def test_wireless() -> None:
    """
    I'm able to get 18-20 MiB/s transfer via WiFi.  That's about 500s for 10GB.
    """
    download_dest = Path(".download")

    print('Establishing BLE connection to first available GoPro...')
    # This doesn't work.  (I had to comment out some code in the SDK)
    # Connect to first available GoPro.
    async with WirelessGoPro(enable_wifi=True) as gopro:
        print('Connected')
        camera_info = await gopro.ble_command.get_hardware_info()
        print(camera_info)

        media_list = await gopro.http_command.get_media_list()
        file_list = media_list.data.files
        print(f'Files available: {len(file_list)}')
        await gopro.http_command.set_turbo_mode(mode=Params.Toggle.ENABLE)
        # TODO: Sort by creation_timestamp, or maybe better by filename (seems to already be sorted anyway)
        # print(media_list.data.files)
        for media_item in file_list:
            print(media_item)
            # media_item.creation_timestamp  -- String.  Looks like epoch timestamp.
            filename = Path(media_item.filename).name
            file_meta = (await gopro.http_command.get_media_metadata(path=media_item.filename)).data
            print(file_meta)
            file_size = int(file_meta.file_size)
            print(f"Downloading {media_item.filename} ({file_size} bytes)")
            local_file = download_dest / filename

            for tries in range(10):
                try:
                    start_time = time.time()
                    await gopro.http_command.download_file(camera_file=media_item.filename, local_file=local_file)
                    elapsed = time.time() - start_time
                    throughput = file_size / 1048576 / elapsed
                    print(f'Download complete in {elapsed}s {throughput} MiB/s')
                    break
                except requests.exceptions.ConnectionError as e:
                    print('[Retrying]')
                    await asyncio.sleep(2)
            # break

        await gopro.http_command.set_turbo_mode(mode=Params.Toggle.DISABLE)

    return
    def _scan_callback(device: BleakDevice, _: Any) -> None:
        # Add to the dict if not unknown
        # if device.name and device.name != "Unknown":
        #     devices[device.name] = device
        print('Scan', device)

    def _filter_callback(device: BleakDevice, ad_data: AdvertisementData) -> bool:
        if not device.name:
            return False

        return device.name.startswith('GoPro')

    # for device in await BleakScanner.discover(timeout=5, detection_callback=_scan_callback):
    #     # if device.name != "Unknown" and device.name is not None:
    #     #     devices[device.name] = device
    #     print('Discover', device.name)
    print("Looking for GoPro on BLE...")
    device = await BleakScanner.find_device_by_filter(_filter_callback)
    print(f"Found BLE device '{device.name}' ({device.address})")

    print('Connecting...')
    async with BleakClient(device) as client:
        print("BLE Connected.")

        print("Pairing...")
        await client.pair()
        print("Paired.")


if __name__ == "__main__":
    asyncio.run(main())