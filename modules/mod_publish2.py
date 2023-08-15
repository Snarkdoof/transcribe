import time
import os
import json
import shutil
import mimetypes
import random

ccmodule = {
    "description": "Publish trials",
    "depends": [],
    "provides": [],
    "inputs": {
        "id": "If any ID",
        "subtitles": "Subtitle file (json)",
        "cast": "Cast file (json)",
        "cards": "Cards file (json) if any",
        "media": "Media file",
        "videofile": "Video file (if any)",
        "mimetype": "Default guess (be aware that mp4 is regarded as video)",
        "webroot": "What part of the destination is the web root (to be removed)",
        "baseurl": "String to append to files for them to be reachable",
        "manifest": "The manifest file to create and publish",
        "dst": "Destination directory for publishing (will update episodes.json)",
        "copymedia": "Copy media files too, default false",
        "rsync": "What rsync statement to run if any (will be appended to 'rsync'",
        "description": "Optional episode description",
        "art": "Art for the episode - if not given, a default is used",
        "published": "Published time (epoch), current time used if not given",
        "update_palette": "Update the palette of the cast from the art, default False",
        "chapters": "File containing chapter info",
        "freshness": "File containing freshness data (for each speaker)",
        "auxfile": "File containing DAR info"
    },
    "outputs": {
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


def make_manifest(id, subs_url, cast_url, media_url, mimetype, art=None,
                  cards=None, chapters=None, freshness=None, auxfile=None,
                  video_url=None):
    manifest = {
        "id": id,
        "subtitles": [{"src": subs_url}],
        "cast": cast_url
    }

    if art:
        manifest["poster"] = art

    if mimetype.startswith("video"):
        manifest["video"] = {"src": media_url}
    else:
        manifest["audio"] = {"src": media_url}
    if cards:
        manifest["info"] = cards
    if chapters:
        manifest["chapters"] = chapters
    if freshness:
        manifest["freshness"] = freshness
    if auxfile:
        manifest["aux"] = auxfile
    if video_url:
        manifest["video"] = {"src": video_url}

    return manifest


def make_episode_entry(id, media_url, title, manifest_url, mimetype,
                       art=None, published=None, description=""):

    if not published:
        published = time.time()

    episode = {
        "id": id,
        "title": title,
        "published": published,
        "manifest": manifest_url,
        "description": description,
        "enclosures": [
            {
                "url": media_url,
                "mime_type": mimetype
            }
        ]
    }

    if art:
        episode["episode_art_url"] = art

    return episode


def merge_episodes(directory, episode):
    # If "episodes.json" already exists, add or update this one, otherwise
    # create new episodes.json

    if not os.path.exists(directory):
        os.makedirs(directory)

    episodesfile = os.path.join(directory, "episodes.json")
    episodes = []
    if os.path.exists(episodesfile):
        with open(episodesfile, "r") as f:
            episodes = json.load(f)

    # Is this an update
    found = False
    for idx, e in enumerate(episodes):
        if e["id"] == episode["id"] or e["manifest"] == episode["manifest"]:
            episodes[idx] = episode
            found = True
            break

    if not found:
        episodes.append(episode)

    # Write back
    if os.path.exists(episodesfile):
        os.rename(episodesfile, episodesfile +".bak")
    with open(episodesfile, "w") as f:
        json.dump(episodes, f, indent=" ")

    return episodesfile, len(episodes)


def process_task(cc, job):

    args = job["args"]

    subtitles = args["subtitles"]
    cast = args["cast"]
    media = args["media"]
    cards = args.get("cards", None)
    manifest = args["manifest"]
    id = args.get("id", random.randint(0,4000000000))
    webroot = args["webroot"]
    dst = args["dst"]
    copymedia = args.get("copymedia", False)
    rsync = args.get("rsync", None)
    mimetype = args.get("mimetype", None)
    baseurl = args.get("baseurl", "")
    title = args.get("title", None)
    art = args.get("art", "https://seer2.itek.norut.no/wp4_poster.jpg")
    published = args.get("published", time.time())
    description = args.get("description", "")
    chapters = args.get("chapters", None)
    freshness = args.get("freshness", None)
    auxfile = args.get("auxfile", None)
    videofile = args.get("videofile", None)

    if not title:
        title = os.path.splitext(os.path.basename(manifest))[0].title()

    if not mimetype:
        mimetype = mimetypes.guess_type(media)[0]

    if not os.path.exists(dst):
        os.makedirs(dst)

    if copymedia:
        dstmedia = os.path.join(dst, os.path.basename(media))
        if os.path.realpath(media) != os.path.realpath(dstmedia):
            cc.log.info("Copying media file to '%s'" % dstmedia)
            shutil.copy(media, dstmedia)

    if args.get("update_palette", False):
        cc.log.debug("Updating palette")
        from palette import Palette
        palette = Palette()
        c = palette.process_file(cast, cast, art, replace=True)

    manifest_url = baseurl + manifest.replace(webroot, "")
    media_url = baseurl + media.replace(webroot, "")
    subtitles_url = baseurl + subtitles.replace(webroot, "")
    cast_url = baseurl + cast.replace(webroot, "")
    video_url = None
    cards_url = None
    if cards:
        cards_url = baseurl + cards.replace(webroot, "")
    if videofile:
        video_url = baseurl + videofile.replace(webroot, "")
    if chapters:
        chapters = baseurl + chapters.replace(webroot, "")
    if freshness:
        freshness = baseurl + freshness.replace(webroot, "")
    if auxfile:
        auxfile = baseurl + auxfile.replace(webroot, "")

    m = make_manifest(id, subtitles_url, cast_url, media_url, mimetype, art=art,
                      cards=cards_url, chapters=chapters, freshness=freshness,
                      auxfile=auxfile, video_url=video_url)
    with open(manifest, "w") as f:
        json.dump(m, f, indent=" ")

    episode = make_episode_entry(m["id"], media_url, title, manifest_url,
                                 mimetype, art, published, description)

    ef, ecount = merge_episodes(dst, episode)

    if rsync:
        import subprocess
        cc.log.info("Running rsync %s" % rsync)
        retval, output = subprocess.getstatusoutput("rsync " + rsync)
        if retval:
            cc.log.error("rsync returned %s" % retval)
            cc.log.error(output)
            raise Exception("rsync failed '%s': %s" % (rsync, output))

    return 100, {"dst": ef, "numepisodes": ecount}
