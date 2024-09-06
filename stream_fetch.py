#!/usr/bin/env python3
import requests
import os
import subprocess
import tempfile
import json
import concurrent.futures

queued = 0
done = 0


def fetch_file(url):
    global queued, done
    queued += 1
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to download {url}")

    response.raise_for_status()  # Ensure successful request

    done += 1
    # print(url, queued, "/", done)
    return response.content


def download_and_concat_ts_files(baseurl, m3u8_url, output_filename="output", parallel=True):
    """
    Downloads an M3U8 playlist and concatenates all TS files with "master" in
    their URLs into a single file.

    Args:
        m3u8_url: URL of the M3U8 playlist. output_filename: Name of the output
        file (default: "output.ts").
    """

    # Download the M3U8 playlist
    response = requests.get(m3u8_url)
    response.raise_for_status()  # Raise an exception if the download fails
    m3u8_content = response.text

    # Extract TS file URLs with "master" in them
    ts_urls = []
    for line in m3u8_content.splitlines():
        if line.startswith("#"):
            continue
        if line.startswith("http"):
            ts_urls.append(line)
        else:
            ts_urls.append(baseurl + "/" + line)

    # We use the extension of the first url for the output filename
    output_filename += os.path.splitext(ts_urls[0])[1]

    # If the segments are the same and they are not ts files, it's time offsets
    # to an mp4 most likely. In that case, just download it
    if ts_urls[0] == ts_urls[-1] and not ts_urls[0].endswith(".ts"):
        print("Single file, downloading it:", ts_urls[0])
        response = requests.get(ts_urls[0])
        response.raise_for_status()
        with open(output_filename, "wb") as outfile:
            outfile.write(response.content)
        return output_filename

    if parallel:
        print("Downloading", len(ts_urls), "files")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(fetch_file, url) for url in ts_urls]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        with open(output_filename, "wb") as outfile:
            for result in results:
                outfile.write(result)
        return output_filename

    # Concatenate TS files
    with open(output_filename, "wb") as outfile:
        for idx, ts_url in enumerate(ts_urls):
            print(f"{output_filename}: {idx}/{len(ts_urls)}")
            ts_response = requests.get(ts_url)
            ts_response.raise_for_status()
            outfile.write(ts_response.content)
    return output_filename


def download_m3u8_from_json(json_data):
    """
    Extracts the M3U8 URL from the given JSON data and downloads the M3U8 file.

    Args:
        json_data: The JSON data (as a dictionary or string).
    """

    if isinstance(json_data, str):
        import json
        data = json.loads(json_data)
    else:
        data = json_data

    m3u8_url = data.get("streamUrls", {}).get("hls")

    if m3u8_url:
        try:
            m3u8_response = requests.get(m3u8_url)
            m3u8_response.raise_for_status()
            return m3u8_url, m3u8_response.content.decode("utf-8")

        except requests.exceptions.RequestException as e:
            print(f"An error occurred while downloading the M3U8 file: {e}")
    else:
        print("No 'hls' key found in the JSON response.")
    raise Exception("No HLS key in the json")


def get_json_from_id(id: str):
    url = f"https://svp.vg.no/svp/api/v1/vgtv/assets/{id}?appName=ailab"
    # Download the json
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def get_shittiest_quality(m3u8_content):
    """
    Parses an M3U8 playlist content and returns the URL of the lowest quality stream.

    Args:
        m3u8_content: The content of the M3U8 playlist as a string.

    Returns:
        The URL of the lowest quality stream, or None if no streams are found.
    """
    lines = m3u8_content.splitlines()
    lowest_bandwidth = float('inf')  # Initialize with infinity
    lowest_quality_url = None

    for i in range(len(lines)):
        if lines[i].startswith("#EXT-X-STREAM-INF:"):
            bandwidth_info = lines[i].split(":")[1]
            bandwidth = int(bandwidth_info.split(",")[0].split("=")[1])

            if bandwidth < lowest_bandwidth:
                lowest_bandwidth = bandwidth
                lowest_quality_url = lines[i + 1]  # The URL is on the next line

    return lowest_quality_url


def get_best_quality(m3u8_content):
    """
    Parses an M3U8 playlist content and returns the URL of the best quality stream.

    Args:
        m3u8_content: The content of the M3U8 playlist as a string.

    Returns:
        The URL of the best quality stream, or None if no streams are found.
    """
    lines = m3u8_content.splitlines()
    highest_bandwidth = 0
    highest_quality_url = None

    for i in range(len(lines)):
        if lines[i].startswith("#EXT-X-STREAM-INF:"):
            bandwidth_info = lines[i].split(":")[1]
            bandwidth = int(bandwidth_info.split(",")[0].split("=")[1])

            if bandwidth > highest_bandwidth:
                highest_bandwidth = bandwidth
                highest_quality_url = lines[i + 1]  # The URL is on the next line

    return highest_quality_url


def do_ffmpeg_magic(filename):
    # Multiple steps.
    # Find all the audio tracks using ffprobe
    p = subprocess.check_output(["ffprobe", "-i", filename, "-show_entries",
                                 "stream=index,codec_type", "-of", "json"])
    info = json.loads(p)

    audio_tracks = [x["index"] for x in info["streams"] if x["codec_type"] == "audio"]

    print("Audio tracks", audio_tracks)
    # If only one, return the filename with no further issues.
    if len(audio_tracks) == 1:
        return filename

    # Extract the audio tracks to temporary files
    tmp_dir = tempfile.mkdtemp()
    tmp_files = []
    for track in audio_tracks:
        tmp_file = os.path.join(tmp_dir, f"audio_{track}.aac")
        tmp_files.append(tmp_file)
        cmd = ["ffmpeg", "-i", filename, "-map", f"0:{track}", "-c:a", "copy", tmp_file]
        print(" ".join(cmd))
        subprocess.run(cmd)

    print("Got temp files", tmp_files)

    # Concat the audio tracks using ffmpeg
    destination = os.path.splitext(filename)[0] + ".aac"
    # We need a temporary file with the list of files to concat
    with open("audio_concat.txt", "w") as f:
        for file in tmp_files:
            f.write(f"file '{file}'\n")
    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", "audio_concat.txt",
                    "-c", "copy", destination])

    # Clean up
    import shutil
    shutil.rmtree(tmp_dir)

    # Should remove the original file too
    os.remove(filename)

    # Return the new filename
    return destination


def download(content_id, directory, output_filename):
    meta = get_json_from_id(content_id)
    m3u8_url, master = download_m3u8_from_json(meta)
    playlist = get_shittiest_quality(master)
    # playlist = get_best_quality(master)

    # The "playlist, possibly with ../ in it, so we need to make it into a full
    # URL using the m3u8_url"
    if playlist.startswith("../"):
        baseurl = m3u8_url.rsplit("/", 2)[0]
        playlist = baseurl + playlist[2:]
    else:
        # Concat with base m3u8 url
        baseurl = m3u8_url.rsplit("/", 1)[0]
        playlist = baseurl + "/" + playlist

    # Now we have a m3u8 playlist that we want to concat
    destination = os.path.join(directory, output_filename)
    # Check for destination, but it can have other extensions, check if there is
    # a file in the cache directory that has the output_filename but any extension
    # and use that instead
    if not os.path.splitext(destination)[1]:
        for file in os.listdir(directory):
            if file.startswith(output_filename):
                destination = os.path.join(directory, file)
                return destination

    print("Downloading")
    try:
        dst = download_and_concat_ts_files(baseurl, playlist,
                                           output_filename=destination)

        # Do fffmpeg stuff if we need to - some (all?) of the .ts files have two
        # different audio tracks, one is the first seconds, the other is the
        # rest. We should concat them really.
        dst = do_ffmpeg_magic(dst)

        return dst
    except Exception:
        import traceback
        traceback.print_exc()
        print(f"Download of {content_id} failed")
        os.remove(destination)

    return None


if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser(description="Download and concatenate TS "
                                     "files from an M3U8 playlist.")
    parser.add_argument("-i", "--input", required=True, help="ID at VG")
    parser.add_argument("-o", "--output", help="Name of the output file")
    parser.add_argument("-d", "--directory", help="Directory to save the file in")
    args = parser.parse_args()

    if not args.output:
        args.output = args.input

    download(args.input, args.directory, args.output)
