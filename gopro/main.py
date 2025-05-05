import re
import sys
import asyncio
import argparse
import os
from typing import Any
from pathlib import Path
import time
import argparse

from bleak import BleakScanner, BleakClient, AdvertisementData
from bleak.backends.device import BLEDevice as BleakDevice
import requests.exceptions

from open_gopro import WirelessGoPro, WiredGoPro, Params

from .media_downloader import MediaDownloader


def main():
    asyncio.run(amain())


# File deletion is possible but not currently part of the SDK: https://github.com/gopro/OpenGoPro/issues/74
#   Will take a little extending to get it working, but seems doable.
async def amain() -> None:
    args = parse_args()
    print(args)
    await test_wired(args.dest_dir)
    # await test_wireless()


def parse_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('dest_dir', nargs='?', default='.download')

    return argparser.parse_args()

async def test_wired(dest_dir: str) -> None:
    """
    Xfer rate is all over the place.  12-41 MiB/s in one case!
    Actually, it really seems to stay fast after the first few files.
    So, wired/USB is the way to go here.  As good as it gets.  WiFi is slower.
    """
    # files_to_download = set((f"100GOPRO/GX0{index}.MP4" for index in range (12481, 12508)))

    # Looking for "_gopro-web._tcp.local."
    # _type=_services._dns-sd._udp.local.
    # name=_gopro-web._tcp.local.

    # If I call
    #         async_browser = AsyncServiceBrowser(
        #     local_zc.zeroconf, _gopro-web._tcp.local., listener=listener
        # )
    # I get back C3501324697549._gopro-web._tcp.local.

    import zeroconf.asyncio
    services = list(await zeroconf.asyncio.AsyncZeroconfServiceTypes.async_find())
    print(services)

    # from zeroconf import ServiceListener
    # class MyServiceListener(ServiceListener):
    #     def add_service(self, zc: 'Zeroconf', type_: str, name: str) -> None:
    #         print("add_service")

    #     def remove_service(self, zc: 'Zeroconf', type_: str, name: str) -> None:
    #         print("remove_service")

    #     def update_service(self, zc: 'Zeroconf', type_: str, name: str) -> None:
    #         print("update_service")

    # listener = MyServiceListener()
    async with zeroconf.asyncio.AsyncZeroconf(unicast=True) as zero_conf:
        info = await zero_conf.async_get_service_info("_gopro-web._tcp.local.", "C3501324697549._gopro-web._tcp.local.")
        print(info)

    async with WiredGoPro() as gopro:
        cam_info = await gopro.http_command.get_camera_info()
        print(cam_info)

        downloader = MediaDownloader(gopro, Path(dest_dir))
        await downloader.download_all_new()


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
