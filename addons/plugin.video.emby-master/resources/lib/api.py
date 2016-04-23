# -*- coding: utf-8 -*-

# Read an api response and convert more complex cases

##################################################################################################

import clientinfo
import utils

##################################################################################################


class API():

    def __init__(self, item):
        # item is the api response
        self.item = item

        self.clientinfo = clientinfo.ClientInfo()
        self.addonName = self.clientinfo.getAddonName()

    def logMsg(self, msg, lvl=1):

        className = self.__class__.__name__
        utils.logMsg("%s %s" % (self.addonName, className), msg, lvl)


    def getUserData(self):
        # Default
        favorite = False
        likes = None
        playcount = None
        played = False
        lastPlayedDate = None
        resume = 0
        userrating = 0

        try:
            userdata = self.item['UserData']

        except KeyError: # No userdata found.
            pass

        else:
            favorite = userdata['IsFavorite']
            likes = userdata.get('Likes')
            # Userrating is based on likes and favourite
            if favorite:
                userrating = 5
            elif likes:
                userrating = 3
            elif likes == False:
                userrating = 0
            else:
                userrating = 1

            lastPlayedDate = userdata.get('LastPlayedDate')
            if lastPlayedDate:
                lastPlayedDate = lastPlayedDate.split('.')[0].replace('T', " ")

            if userdata['Played']:
                # Playcount is tied to the watch status
                played = True
                playcount = userdata['PlayCount']
                if playcount == 0:
                    playcount = 1

                if lastPlayedDate is None:
                    lastPlayedDate = self.getDateCreated()

            playbackPosition = userdata.get('PlaybackPositionTicks')
            if playbackPosition:
                resume = playbackPosition / 10000000.0

        return {

            'Favorite': favorite,
            'Likes': likes,
            'PlayCount': playcount,
            'Played': played,
            'LastPlayedDate': lastPlayedDate,
            'Resume': resume,
            'UserRating': userrating
        }

    def getPeople(self):
        # Process People
        director = []
        writer = []
        cast = []

        try:
            people = self.item['People']

        except KeyError:
            pass

        else:
            for person in people:

                type = person['Type']
                name = person['Name']

                if "Director" in type:
                    director.append(name)
                elif "Actor" in type:
                    cast.append(name)
                elif type in ("Writing", "Writer"):
                    writer.append(name)

        return {

            'Director': director,
            'Writer': writer,
            'Cast': cast
        }

    def getMediaStreams(self):
        videotracks = []
        audiotracks = []
        subtitlelanguages = []

        try:
            media_streams = self.item['MediaSources'][0]['MediaStreams']

        except KeyError:
            if not self.item.get("MediaStreams"): return None
            media_streams = self.item['MediaStreams']

        for media_stream in media_streams:
            # Sort through Video, Audio, Subtitle
            stream_type = media_stream['Type']
            codec = media_stream.get('Codec', "").lower()
            profile = media_stream.get('Profile', "").lower()

            if stream_type == "Video":
                # Height, Width, Codec, AspectRatio, AspectFloat, 3D
                track = {

                    'codec': codec,
                    'height': media_stream.get('Height'),
                    'width': media_stream.get('Width'),
                    'video3DFormat': self.item.get('Video3DFormat'),
                    'aspect': 1.85
                }

                try:
                    container = self.item['MediaSources'][0]['Container'].lower()
                except:
                    container = ""

                # Sort codec vs container/profile
                if "msmpeg4" in codec:
                    track['codec'] = "divx"
                elif "mpeg4" in codec:
                    if "simple profile" in profile or not profile:
                        track['codec'] = "xvid"
                elif "h264" in codec:
                    if container in ("mp4", "mov", "m4v"):
                        track['codec'] = "avc1"

                # Aspect ratio
                if self.item.get('AspectRatio'):
                    # Metadata AR
                    aspect = self.item['AspectRatio']
                else: # File AR
                    aspect = media_stream.get('AspectRatio', "0")

                try:
                    aspectwidth, aspectheight = aspect.split(':')
                    track['aspect'] = round(float(aspectwidth) / float(aspectheight), 6)

                except (ValueError, ZeroDivisionError):
                    width = track.get('width')
                    height = track.get('height')

                    if width and height:
                        track['aspect'] = round(float(width / height), 6)
                    else:
                        track['aspect'] = 1.85

                if self.item.get("RunTimeTicks"):
                    track['duration'] = self.item.get("RunTimeTicks") / 10000000.0

                videotracks.append(track)

            elif stream_type == "Audio":
                # Codec, Channels, language
                track = {

                    'codec': codec,
                    'channels': media_stream.get('Channels'),
                    'language': media_stream.get('Language')
                }

                if "dca" in codec and "dts-hd ma" in profile:
                    track['codec'] = "dtshd_ma"

                audiotracks.append(track)

            elif stream_type == "Subtitle":
                # Language
                subtitlelanguages.append(media_stream.get('Language', "Unknown"))

        return {

            'video': videotracks,
            'audio': audiotracks,
            'subtitle': subtitlelanguages
        }

    def getRuntime(self):
        try:
            runtime = self.item['RunTimeTicks'] / 10000000.0

        except KeyError:
            runtime = self.item.get('CumulativeRunTimeTicks', 0) / 10000000.0

        return runtime

    def adjustResume(self, resume_seconds):

        resume = 0
        if resume_seconds:
            resume = round(float(resume_seconds), 6)
            jumpback = int(utils.settings('resumeJumpBack'))
            if resume > jumpback:
                # To avoid negative bookmark
                resume = resume - jumpback

        return resume

    def getStudios(self):
        # Process Studios
        studios = []

        try:
            studio = self.item['SeriesStudio']
            studios.append(self.verifyStudio(studio))

        except KeyError:
            studioList = self.item['Studios']
            for studio in studioList:

                name = studio['Name']
                studios.append(self.verifyStudio(name))

        return studios

    def verifyStudio(self, studioName):
        # Convert studio for Kodi to properly detect them
        studios = {

            'abc (us)': "ABC",
            'fox (us)': "FOX",
            'mtv (us)': "MTV",
            'showcase (ca)': "Showcase",
            'wgn america': "WGN"
        }

        return studios.get(studioName.lower(), studioName)

    def getChecksum(self):
        # Use the etags checksum and userdata
        userdata = self.item['UserData']

        checksum = "%s%s%s%s%s%s%s" % (

            self.item['Etag'],
            userdata['Played'],
            userdata['IsFavorite'],
            userdata.get('Likes',''),
            userdata['PlaybackPositionTicks'],
            userdata.get('UnplayedItemCount', ""),
            userdata.get('LastPlayedDate', "")
        )

        return checksum

    def getGenres(self):
        all_genres = ""
        genres = self.item.get('Genres', self.item.get('SeriesGenres'))

        if genres:
            all_genres = " / ".join(genres)

        return all_genres

    def getDateCreated(self):

        try:
            dateadded = self.item['DateCreated']
            dateadded = dateadded.split('.')[0].replace('T', " ")
        except KeyError:
            dateadded = None

        return dateadded

    def getPremiereDate(self):

        try:
            premiere = self.item['PremiereDate']
            premiere = premiere.split('.')[0].replace('T', " ")
        except KeyError:
            premiere = None

        return premiere

    def getOverview(self):

        try:
            overview = self.item['Overview']
            overview = overview.replace("\"", "\'")
            overview = overview.replace("\n", " ")
            overview = overview.replace("\r", " ")
        except KeyError:
            overview = ""

        return overview

    def getTagline(self):

        try:
            tagline = self.item['Taglines'][0]
        except IndexError:
            tagline = None

        return tagline

    def getProvider(self, providername):

        try:
            provider = self.item['ProviderIds'][providername]
        except KeyError:
            provider = None

        return provider

    def getMpaa(self):
        # Convert more complex cases
        mpaa = self.item.get('OfficialRating', "")

        if mpaa in ("NR", "UR"):
            # Kodi seems to not like NR, but will accept Not Rated
            mpaa = "Not Rated"

        return mpaa

    def getCountry(self):

        try:
            country = self.item['ProductionLocations'][0]
        except IndexError:
            country = None

        return country

    def getFilePath(self):

        try:
            filepath = self.item['Path']

        except KeyError:
            filepath = ""

        else:
            if "\\\\" in filepath:
                # append smb protocol
                filepath = filepath.replace("\\\\", "smb://")
                filepath = filepath.replace("\\", "/")

            if self.item.get('VideoType'):
                videotype = self.item['VideoType']
                # Specific format modification
                if 'Dvd'in videotype:
                    filepath = "%s/VIDEO_TS/VIDEO_TS.IFO" % filepath
                elif 'BluRay' in videotype:
                    filepath = "%s/BDMV/index.bdmv" % filepath

            if "\\" in filepath:
                # Local path scenario, with special videotype
                filepath = filepath.replace("/", "\\")

        return filepath
