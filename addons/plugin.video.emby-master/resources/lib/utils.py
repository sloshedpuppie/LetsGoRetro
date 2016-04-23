# -*- coding: utf-8 -*-

#################################################################################################

import cProfile
import inspect
import json
import pstats
import sqlite3
import StringIO
import os
from datetime import datetime, time
import time
import unicodedata
import xml.etree.ElementTree as etree

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

#################################################################################################


def logMsg(title, msg, level=1):

    # Get the logLevel set in UserClient
    try:
        logLevel = int(window('emby_logLevel'))
    except ValueError:
        logLevel = 0

    if logLevel >= level:

        if logLevel == 2: # inspect.stack() is expensive
            try:
                xbmc.log("%s -> %s : %s" % (title, inspect.stack()[1][3], msg))
            except UnicodeEncodeError:
                xbmc.log("%s -> %s : %s" % (title, inspect.stack()[1][3], msg.encode('utf-8')))
        else:
            try:
                xbmc.log("%s -> %s" % (title, msg))
            except UnicodeEncodeError:
                xbmc.log("%s -> %s" % (title, msg.encode('utf-8')))

def window(property, value=None, clear=False, windowid=10000):
    # Get or set window property
    WINDOW = xbmcgui.Window(windowid)

    #setproperty accepts both string and unicode but utf-8 strings are adviced by kodi devs because some unicode can give issues
    '''if isinstance(property, unicode):
        property = property.encode("utf-8")
    if isinstance(value, unicode):
        value = value.encode("utf-8")'''

    if clear:
        WINDOW.clearProperty(property)
    elif value is not None:
        WINDOW.setProperty(property, value)
    else: #getproperty returns string so convert to unicode
        return WINDOW.getProperty(property)#.decode("utf-8")

def settings(setting, value=None):
    # Get or add addon setting
    if value is not None:
        xbmcaddon.Addon(id='plugin.video.emby').setSetting(setting, value)
    else:
        return xbmcaddon.Addon(id='plugin.video.emby').getSetting(setting) #returns unicode object

def language(stringid):
    # Central string retrieval
    string = xbmcaddon.Addon(id='plugin.video.emby').getLocalizedString(stringid) #returns unicode object
    return string

def kodiSQL(media_type="video"):

    if media_type == "emby":
        dbPath = xbmc.translatePath("special://database/emby.db").decode('utf-8')
    elif media_type == "music":
        dbPath = getKodiMusicDBPath()
    elif media_type == "texture":
        dbPath = xbmc.translatePath("special://database/Textures13.db").decode('utf-8')
    else:
        dbPath = getKodiVideoDBPath()

    connection = sqlite3.connect(dbPath)
    return connection

def getKodiVideoDBPath():

    dbVersion = {

        "13": 78,   # Gotham
        "14": 90,   # Helix
        "15": 93,   # Isengard
        "16": 99,   # Jarvis
        "17": 104   # Krypton
    }

    dbPath = xbmc.translatePath(
                    "special://database/MyVideos%s.db"
                    % dbVersion.get(xbmc.getInfoLabel('System.BuildVersion')[:2], "")).decode('utf-8')
    return dbPath

def getKodiMusicDBPath():

    dbVersion = {

        "13": 46,   # Gotham
        "14": 48,   # Helix
        "15": 52,   # Isengard
        "16": 56,   # Jarvis
        "17": 60    # Krypton
    }

    dbPath = xbmc.translatePath(
                    "special://database/MyMusic%s.db"
                    % dbVersion.get(xbmc.getInfoLabel('System.BuildVersion')[:2], "")).decode('utf-8')
    return dbPath

def getScreensaver():
    # Get the current screensaver value
    query = {

        'jsonrpc': "2.0",
        'id': 0,
        'method': "Settings.getSettingValue",
        'params': {

            'setting': "screensaver.mode"
        }
    }
    return json.loads(xbmc.executeJSONRPC(json.dumps(query)))['result']['value']

def setScreensaver(value):
    # Toggle the screensaver
    query = {

        'jsonrpc': "2.0",
        'id': 0,
        'method': "Settings.setSettingValue",
        'params': {

            'setting': "screensaver.mode",
            'value': value
        }
    }
    logMsg("EMBY", "Toggling screensaver: %s %s" % (value, xbmc.executeJSONRPC(json.dumps(query))), 1)

def reset():

    dialog = xbmcgui.Dialog()

    if dialog.yesno("Warning", "Are you sure you want to reset your local Kodi database?") == 0:
        return

    # first stop any db sync
    window('emby_shouldStop', value="true")
    count = 10
    while window('emby_dbScan') == "true":
        logMsg("EMBY", "Sync is running, will retry: %s..." % count)
        count -= 1
        if count == 0:
            dialog.ok("Warning", "Could not stop the database from running. Try again.")
            return
        xbmc.sleep(1000)

    # Clean up the playlists
    deletePlaylists()

    # Clean up the video nodes
    deleteNodes()

    # Wipe the kodi databases
    logMsg("EMBY", "Resetting the Kodi video database.", 0)
    connection = kodiSQL('video')
    cursor = connection.cursor()
    cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
    rows = cursor.fetchall()
    for row in rows:
        tablename = row[0]
        if tablename != "version":
            cursor.execute("DELETE FROM " + tablename)
    connection.commit()
    cursor.close()

    if settings('enableMusic') == "true":
        logMsg("EMBY", "Resetting the Kodi music database.")
        connection = kodiSQL('music')
        cursor = connection.cursor()
        cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
        rows = cursor.fetchall()
        for row in rows:
            tablename = row[0]
            if tablename != "version":
                cursor.execute("DELETE FROM " + tablename)
        connection.commit()
        cursor.close()

    # Wipe the emby database
    logMsg("EMBY", "Resetting the Emby database.", 0)
    connection = kodiSQL('emby')
    cursor = connection.cursor()
    cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
    rows = cursor.fetchall()
    for row in rows:
        tablename = row[0]
        if tablename != "version":
            cursor.execute("DELETE FROM " + tablename)
    cursor.execute('DROP table IF EXISTS emby')
    cursor.execute('DROP table IF EXISTS view')
    connection.commit()
    cursor.close()

    # Offer to wipe cached thumbnails
    resp = dialog.yesno("Warning", "Remove all cached artwork?")
    if resp:
        logMsg("EMBY", "Resetting all cached artwork.", 0)
        # Remove all existing textures first
        path = xbmc.translatePath("special://thumbnails/").decode('utf-8')
        if xbmcvfs.exists(path):
            allDirs, allFiles = xbmcvfs.listdir(path)
            for dir in allDirs:
                allDirs, allFiles = xbmcvfs.listdir(path+dir)
                for file in allFiles:
                    if os.path.supports_unicode_filenames:
                        xbmcvfs.delete(os.path.join(path+dir.decode('utf-8'),file.decode('utf-8')))
                    else:
                        xbmcvfs.delete(os.path.join(path.encode('utf-8')+dir,file))

        # remove all existing data from texture DB
        connection = kodiSQL('texture')
        cursor = connection.cursor()
        cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
        rows = cursor.fetchall()
        for row in rows:
            tableName = row[0]
            if(tableName != "version"):
                cursor.execute("DELETE FROM " + tableName)
        connection.commit()
        cursor.close()

    # reset the install run flag
    settings('SyncInstallRunDone', value="false")

    # Remove emby info
    resp = dialog.yesno("Warning", "Reset all Emby Addon settings?")
    if resp:
        # Delete the settings
        addon = xbmcaddon.Addon()
        addondir = xbmc.translatePath(addon.getAddonInfo('profile')).decode('utf-8')
        dataPath = "%ssettings.xml" % addondir
        xbmcvfs.delete(dataPath)
        logMsg("EMBY", "Deleting: settings.xml", 1)

    dialog.ok(
        heading="Emby for Kodi",
        line1="Database reset has completed, Kodi will now restart to apply the changes.")
    xbmc.executebuiltin('RestartApp')

def profiling(sortby="cumulative"):
    # Will print results to Kodi log
    def decorator(func):
        def wrapper(*args, **kwargs):

            pr = cProfile.Profile()

            pr.enable()
            result = func(*args, **kwargs)
            pr.disable()

            s = StringIO.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            logMsg("EMBY Profiling", s.getvalue(), 1)

            return result

        return wrapper
    return decorator

def convertdate(date):
    try:
        date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    except TypeError:
        # TypeError: attribute of type 'NoneType' is not callable
        # Known Kodi/python error
        date = datetime(*(time.strptime(date, "%Y-%m-%dT%H:%M:%SZ")[0:6]))

    return date

def normalize_nodes(text):
    # For video nodes
    text = text.replace(":", "")
    text = text.replace("/", "-")
    text = text.replace("\\", "-")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("*", "")
    text = text.replace("?", "")
    text = text.replace('|', "")
    text = text.replace('(', "")
    text = text.replace(')', "")
    text = text.strip()
    # Remove dots from the last character as windows can not have directories
    # with dots at the end
    text = text.rstrip('.')
    text = unicodedata.normalize('NFKD', unicode(text, 'utf-8')).encode('ascii', 'ignore')

    return text

def normalize_string(text):
    # For theme media, do not modify unless
    # modified in TV Tunes
    text = text.replace(":", "")
    text = text.replace("/", "-")
    text = text.replace("\\", "-")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("*", "")
    text = text.replace("?", "")
    text = text.replace('|', "")
    text = text.strip()
    # Remove dots from the last character as windows can not have directories
    # with dots at the end
    text = text.rstrip('.')
    text = unicodedata.normalize('NFKD', unicode(text, 'utf-8')).encode('ascii', 'ignore')

    return text

def indent(elem, level=0):
    # Prettify xml trees
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
          elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
          elem.tail = i
        for elem in elem:
          indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
          elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
          elem.tail = i

def sourcesXML():
    # To make Master lock compatible
    path = xbmc.translatePath("special://profile/").decode('utf-8')
    xmlpath = "%ssources.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except: # Document is blank or missing
        root = etree.Element('sources')
    else:
        root = xmlparse.getroot()


    video = root.find('video')
    if video is None:
        video = etree.SubElement(root, 'video')
        etree.SubElement(video, 'default', attrib={'pathversion': "1"})

    # Add elements
    count = 2
    for source in root.findall('.//path'):
        if source.text == "smb://":
            count -= 1

        if count == 0:
            # sources already set
            break
    else:
        # Missing smb:// occurences, re-add.
        for i in range(0, count):
            source = etree.SubElement(video, 'source')
            etree.SubElement(source, 'name').text = "Emby"
            etree.SubElement(source, 'path', attrib={'pathversion': "1"}).text = "smb://"
            etree.SubElement(source, 'allowsharing').text = "true"
    # Prettify and write to file
    try:
        indent(root)
    except: pass
    etree.ElementTree(root).write(xmlpath)

def passwordsXML():

    # To add network credentials
    path = xbmc.translatePath("special://userdata/").decode('utf-8')
    xmlpath = "%spasswords.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except: # Document is blank or missing
        root = etree.Element('passwords')
    else:
        root = xmlparse.getroot()

    dialog = xbmcgui.Dialog()
    credentials = settings('networkCreds')
    if credentials:
        # Present user with options
        option = dialog.select("Modify/Remove network credentials", ["Modify", "Remove"])

        if option < 0:
            # User cancelled dialog
            return

        elif option == 1:
            # User selected remove
            for paths in root.getiterator('passwords'):
                for path in paths:
                    if path.find('.//from').text == "smb://%s/" % credentials:
                        paths.remove(path)
                        logMsg("EMBY", "Successfully removed credentials for: %s"
                                % credentials, 1)
                        etree.ElementTree(root).write(xmlpath)
                        break
            else:
                logMsg("EMBY", "Failed to find saved server: %s in passwords.xml" % credentials, 1)

            settings('networkCreds', value="")
            xbmcgui.Dialog().notification(
                                heading="Emby for Kodi",
                                message="%s removed from passwords.xml" % credentials,
                                icon="special://home/addons/plugin.video.emby/icon.png",
                                time=1000,
                                sound=False)
            return

        elif option == 0:
            # User selected to modify
            server = dialog.input("Modify the computer name or ip address", credentials)
            if not server:
                return
    else:
        # No credentials added
        dialog.ok(
            heading="Network credentials",
            line1= (
                "Input the server name or IP address as indicated in your emby library paths. "
                'For example, the server name: \\\\SERVER-PC\\path\\ is "SERVER-PC".'))
        server = dialog.input("Enter the server name or IP address")
        if not server:
            return

    # Network username
    user = dialog.input("Enter the network username")
    if not user:
        return
    # Network password
    password = dialog.input(
                        heading="Enter the network password",
                        option=xbmcgui.ALPHANUM_HIDE_INPUT)
    if not password:
        return

    # Add elements
    for path in root.findall('.//path'):
        if path.find('.//from').text.lower() == "smb://%s/" % server.lower():
            # Found the server, rewrite credentials
            path.find('.//to').text = "smb://%s:%s@%s/" % (user, password, server)
            break
    else:
        # Server not found, add it.
        path = etree.SubElement(root, 'path')
        etree.SubElement(path, 'from', attrib={'pathversion': "1"}).text = "smb://%s/" % server
        topath = "smb://%s:%s@%s/" % (user, password, server)
        etree.SubElement(path, 'to', attrib={'pathversion': "1"}).text = topath
        # Force Kodi to see the credentials without restarting
        xbmcvfs.exists(topath)

    # Add credentials
    settings('networkCreds', value="%s" % server)
    logMsg("EMBY", "Added server: %s to passwords.xml" % server, 1)
    # Prettify and write to file
    try:
        indent(root)
    except: pass
    etree.ElementTree(root).write(xmlpath)

    dialog.notification(
            heading="Emby for Kodi",
            message="%s added to passwords.xml" % server,
            icon="special://home/addons/plugin.video.emby/icon.png",
            time=1000,
            sound=False)

def playlistXSP(mediatype, tagname, viewid, viewtype="", delete=False):
    # Tagname is in unicode - actions: add or delete
    tagname = tagname.encode('utf-8')

    path = xbmc.translatePath("special://profile/playlists/video/").decode('utf-8')
    if viewtype == "mixed":
        plname = "%s - %s" % (tagname, mediatype)
        xsppath = "%sEmby %s - %s.xsp" % (path, viewid, mediatype)
    else:
        plname = tagname
        xsppath = "%sEmby %s.xsp" % (path, viewid)

    # Create the playlist directory
    if not xbmcvfs.exists(path):
        logMsg("EMBY", "Creating directory: %s" % path, 1)
        xbmcvfs.mkdirs(path)

    # Only add the playlist if it doesn't already exists
    if xbmcvfs.exists(xsppath):

        if delete:
            xbmcvfs.delete(xsppath)
            logMsg("EMBY", "Successfully removed playlist: %s." % tagname, 1)

        return

    # Using write process since there's no guarantee the xml declaration works with etree
    itemtypes = {
        'homevideos': "movies"
    }
    logMsg("EMBY", "Writing playlist file to: %s" % xsppath, 1)
    try:
        f = xbmcvfs.File(xsppath, 'w')
    except:
        logMsg("EMBY", "Failed to create playlist: %s" % xsppath, 1)
        return
    else:
        f.write(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
            '<smartplaylist type="%s">\n\t'
                '<name>Emby %s</name>\n\t'
                '<match>all</match>\n\t'
                '<rule field="tag" operator="is">\n\t\t'
                    '<value>%s</value>\n\t'
                '</rule>'
            '</smartplaylist>'
            % (itemtypes.get(mediatype, mediatype), plname, tagname))
        f.close()
    logMsg("EMBY", "Successfully added playlist: %s" % tagname)

def deletePlaylists():

    # Clean up the playlists
    path = xbmc.translatePath("special://profile/playlists/video/").decode('utf-8')
    dirs, files = xbmcvfs.listdir(path)
    for file in files:
        if file.decode('utf-8').startswith('Emby'):
            xbmcvfs.delete("%s%s" % (path, file))

def deleteNodes():

    # Clean up video nodes
    import shutil
    path = xbmc.translatePath("special://profile/library/video/").decode('utf-8')
    dirs, files = xbmcvfs.listdir(path)
    for dir in dirs:
        if dir.decode('utf-8').startswith('Emby'):
            try:
                shutil.rmtree("%s%s" % (path, dir.decode('utf-8')))
            except:
                logMsg("EMBY", "Failed to delete directory: %s" % dir.decode('utf-8'))
    for file in files:
        if file.decode('utf-8').startswith('emby'):
            try:
                xbmcvfs.delete("%s%s" % (path, file.decode('utf-8')))
            except:
                logMsg("EMBY", "Failed to file: %s" % file.decode('utf-8'))
