
import urllib.request
import os

try:
    import podcastparser
    CANRUN = True
except Exception:
    CANRUN = False
    print("Missing podcastparser")


ccmodule = {
    "description": "Parse RSS feeds and generate jobs based on it",
    "depends": [],
    "provides": [],
    "inputs": {
        "src": "RSS source (url)",
        "max_process": "Post maximum this amount of episodes",
        "dst": "Destination directory",
        "reprocess": "True to force reprocessing",
        "dst_ext": "Extension of destination file (for caching)"
    },
    "outputs": {
        "dst": "Output directory (ID appended)",
        "itemid": "The program ID",
        "dst_files": "Final destination files",
        "episodes": "List of episodes to process"
    },
    "defaults": {
        "priority": 50,  # Normal
        "runOn": "success"
    },
    "status": {
        "progress": "Progress 0-100%",
        "state": "Current state of processing"
    }
}


# class RSSPoster:
#     def __init__(self, url):
#        self.parsed = podcastparser.parse(feedurl, urllib.request.urlopen(feedurl))


def process_task(cc, job):

    args = job["args"]
    source = args["src"]
    dst = args.get("dst", "/tmp/rss")
    max_process = int(args.get("max_process", 0))
    reprocess = args.get("reprocess", False)

    try:
        import podcastparser
        parsed = podcastparser.parse(source, urllib.request.urlopen(source, capath="/etc/ssl/certs"))
    except Exception:
        cc.log.exception("Failed to parse url '%s'" % source)
        raise Exception("Failed to parse url '%s'" % source)

    # Append the title to the destination dir
    print(" *** Processing", parsed["title"], "at", dst)
    dst = os.path.join(dst, parsed["title"].replace(" ", "_"))
    itemid = parsed["title"].replace(" ", "_")

    # Check episodes
    episodes = []
    dst_files = []
    num_posts = 0

    for episode in parsed["episodes"]:
        einfo = episode
        einfo["id"] = episode.get("guid", episode["published"])
        for enclosure in episode["enclosures"]:
            if enclosure["mime_type"].startswith("audio"):
                einfo.update({k: enclosure[k] for k in enclosure})
                break

        path = os.path.join(dst, einfo["id"])
        einfo["path"] = os.path.splitext(path)[0] + args.get("dst_ext", ".json")
        einfo["processed"] = os.path.exists(einfo["path"]) and not reprocess

        episodes.append(einfo)
        dst_files.append(einfo["path"])

        if max_process:  # not einfo["processed"] and max_process:
            num_posts += 1

            if num_posts >= max_process:
                break

    return 100, {"dst": dst, "episodes": episodes, "dst_files": dst_files, "itemid": itemid}

