# -*- coding: utf-8 -*-

#################################################################################################

import json

import xbmc
import xbmcgui
import xbmcplugin

import clientinfo
import playutils
import playbackutils
import embydb_functions as embydb
import read_embyserver as embyserver
import utils

#################################################################################################


class Playlist():


    def __init__(self):

        self.clientInfo = clientinfo.ClientInfo()
        self.addonName = self.clientInfo.getAddonName()

        self.userid = utils.window('emby_currUser')
        self.server = utils.window('emby_server%s' % self.userid)

        self.emby = embyserver.Read_EmbyServer()

    def logMsg(self, msg, lvl=1):

        self.className = self.__class__.__name__
        utils.logMsg("%s %s" % (self.addonName, self.className), msg, lvl)


    def playAll(self, itemids, startat):

        window = utils.window

        embyconn = utils.kodiSQL('emby')
        embycursor = embyconn.cursor()
        emby_db = embydb.Embydb_Functions(embycursor)

        player = xbmc.Player()
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()

        self.logMsg("---*** PLAY ALL ***---", 1)
        self.logMsg("Items: %s and start at: %s" % (itemids, startat), 1)

        started = False
        window('emby_customplaylist', value="true")

        if startat != 0:
            # Seek to the starting position
            window('emby_customplaylist.seektime', str(startat))

        for itemid in itemids:
            embydb_item = emby_db.getItem_byId(itemid)
            try:
                dbid = embydb_item[0]
                mediatype = embydb_item[4]
            except TypeError:
                # Item is not found in our database, add item manually
                self.logMsg("Item was not found in the database, manually adding item.", 1)
                item = self.emby.getItem(itemid)
                self.addtoPlaylist_xbmc(playlist, item)
            else:
                # Add to playlist
                self.addtoPlaylist(dbid, mediatype)

            self.logMsg("Adding %s to playlist." % itemid, 1)

            if not started:
                started = True
                player.play(playlist)

        self.verifyPlaylist()
        embycursor.close()

    def modifyPlaylist(self, itemids):

        embyconn = utils.kodiSQL('emby')
        embycursor = embyconn.cursor()
        emby_db = embydb.Embydb_Functions(embycursor)

        self.logMsg("---*** ADD TO PLAYLIST ***---", 1)
        self.logMsg("Items: %s" % itemids, 1)

        player = xbmc.Player()
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)

        for itemid in itemids:
            embydb_item = emby_db.getItem_byId(itemid)
            try:
                dbid = embydb_item[0]
                mediatype = embydb_item[4]
            except TypeError:
                # Item is not found in our database, add item manually
                item = self.emby.getItem(itemid)
                self.addtoPlaylist_xbmc(playlist, item)
            else:
                # Add to playlist
                self.addtoPlaylist(dbid, mediatype)

            self.logMsg("Adding %s to playlist." % itemid, 1)

        self.verifyPlaylist()
        embycursor.close()
        return playlist
    
    def addtoPlaylist(self, dbid=None, mediatype=None, url=None):

        pl = {

            'jsonrpc': "2.0",
            'id': 1,
            'method': "Playlist.Add",
            'params': {

                'playlistid': 1
            }
        }
        if dbid is not None:
            pl['params']['item'] = {'%sid' % mediatype: int(dbid)}
        else:
            pl['params']['item'] = {'file': url}

        self.logMsg(xbmc.executeJSONRPC(json.dumps(pl)), 2)

    def addtoPlaylist_xbmc(self, playlist, item):

        playurl = playutils.PlayUtils(item).getPlayUrl()
        if not playurl:
            # Playurl failed
            self.logMsg("Failed to retrieve playurl.", 1)
            return

        self.logMsg("Playurl: %s" % playurl)
        listitem = xbmcgui.ListItem()
        playbackutils.PlaybackUtils(item).setProperties(playurl, listitem)

        playlist.add(playurl, listitem)

    def insertintoPlaylist(self, position, dbid=None, mediatype=None, url=None):

        pl = {

            'jsonrpc': "2.0",
            'id': 1,
            'method': "Playlist.Insert",
            'params': {

                'playlistid': 1,
                'position': position
            }
        }
        if dbid is not None:
            pl['params']['item'] = {'%sid' % mediatype: int(dbid)}
        else:
            pl['params']['item'] = {'file': url}

        self.logMsg(xbmc.executeJSONRPC(json.dumps(pl)), 2)

    def verifyPlaylist(self):

        pl = {

            'jsonrpc': "2.0",
            'id': 1,
            'method': "Playlist.GetItems",
            'params': {

                'playlistid': 1
            }
        }
        self.logMsg(xbmc.executeJSONRPC(json.dumps(pl)), 2)

    def removefromPlaylist(self, position):

        pl = {

            'jsonrpc': "2.0",
            'id': 1,
            'method': "Playlist.Remove",
            'params': {

                'playlistid': 1,
                'position': position
            }
        }
        self.logMsg(xbmc.executeJSONRPC(json.dumps(pl)), 2)
