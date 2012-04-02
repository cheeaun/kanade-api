#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import re, cgi, logging
from datetime import datetime, timedelta

import webapp2, json
from google.appengine.ext import db
from google.appengine.api import urlfetch, memcache

from bs4 import BeautifulSoup

MALAPI = 'http://mal-api.com/anime/'
MALSITE = 'http://myanimelist.net/anime/'

class AnimeV1(db.Model):
    id = db.StringProperty(required=True)
    title = db.StringProperty(required=True)
    image = db.StringProperty(required=True)
    score = db.FloatProperty(required=True)
    episodes = db.IntegerProperty()
    genres = db.StringListProperty()
    updated_datetime = db.DateTimeProperty(auto_now=True)

class MainHandler(webapp2.RequestHandler):
    def get(self):
        self.response.out.write('<!DOCTYPE html>\
<title>Kanade</title>\
<style>body{font-family: helvetica, arial, sans-serif; width: 320px; margin: 50px auto; font-size: 14px; line-height: 1.4em;}</style>\
<p>Hi there. I\'m Kanade.</p>\
<p>I am an API which gives you data of anime series with information such as scores, genres &amp; episode count. Here\'s a simple example: <a href="/v1/anime?id=21">/v1/anime?id=21</a></p>\
<p>I am powered by <a href="http://mal-api.com/">MyAnimeList Unofficial API</a>, <a href="http://myanimelist.net/">MyAnimeList</a> itself &amp; <a href="http://code.google.com/appengine/">Google App Engine</a>.</p>\
<p><a href="http://twitter.com/cheeaun">@cheeaun</a> &middot; <a href="http://github.com/cheeaun/kanade-api">GitHub</a></p>')

class AnimeV1Handler(webapp2.RequestHandler):
    def get(self):
        id = cgi.escape(self.request.get('id'))
        callback = cgi.escape(self.request.get('callback'))
        reset = cgi.escape(self.request.get('_reset'))
        
        response = {'ok': True, 'result': None}
        
        if re.match(r"^\d+$", id):
            content = memcache.get(id)
            if content is not None and not reset:
                response['result'] = content
            else:
                q = db.GqlQuery('select * from AnimeV1 where id = :1', id)
                result = q.get()
                originalScore = None
                if result is not None: originalScore = result.score
                if result is not None and (datetime.now() - result.updated_datetime <= timedelta(hours=24)):
                    content = {
                        'id': result.id,
                        'title': result.title,
                        'image': result.image,
                        'score': result.score,
                        'episodes': result.episodes,
                        'genres': result.genres
                    }
                    response['result'] = content
                    memcache.set(id, content, 43200)
                else:
                    try:
                        result = urlfetch.fetch(MALAPI + id, deadline = 10)
                        if result.status_code == 200:
                            content = formatResponse(result.content)
                            response['result'] = content
                            storeAnimeV1(id, content)
                            if originalScore is not None and content['score'] != originalScore:
                                logging.info('Anime Score Change: ' + content['title'] + ' ' + id + ': ' + str(originalScore) + ' -> ' + str(content['score']))
                        else:
                            raise urlfetch.Error()
                    except urlfetch.Error:
                        # Try one more time before giving up
                        try:
                            result = urlfetch.fetch(MALSITE + id, deadline = 10, allow_truncated = True)
                            if result.status_code == 200:
                                content = formatResponse(result.content, True)
                                if content is None:
                                    raise urlfetch.Error()
                                    return
                                response['result'] = content
                                storeAnimeV1(id, content)
                                if originalScore is not None and content['score'] != originalScore:
                                    logging.info('Anime Score Change: ' + content['title'] + ' ' + id + ': ' + str(originalScore) + ' -> ' + str(content['score']))
                            else:
                                raise urlfetch.Error()
                        except urlfetch.Error:
                            response['ok'] = False
        else:
            response['ok'] = False
        
        jsonData = json.dumps(response, sort_keys=True)
        if callback and re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*?$', callback): 
            jsonData = callback + '(' + jsonData + ')'
        
        if response['ok'] is True and response['result'] is not None:
            self.response.headers['Cache-Control'] = 'public; max-age=43200'
        self.response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        self.response.headers['Vary'] = 'Accept-Encoding'
        self.response.headers['Proxy-Connection'] = 'Keep-Alive'
        self.response.headers['Connection'] = 'Keep-Alive'
        self.response.out.write(jsonData)

def formatResponse(content, html=False):
    if html:
        # The ugly way to parse ugly HTML
        
        match = re.search(r'<h1>\s*<div[^<>]*>[^<>]*</div>\s*([^<>]+)\s*<', content, re.I | re.U)
        title = match.group(1).decode('utf-8') if match else None
        if title is None: return None
        
        match = re.search(r'">\s*<img\s+src="([^"<>\s]+)', content, re.I)
        image = match.group(1) if match else None
        print image
        if image is None: return None
        
        match = re.search(r'Score:\s*</span>\s*([\d.]+)\s*<', content, re.I)
        score = float(match.group(1)) if match else 0
        
        match = re.search(r'Episodes:\s*</span>\s*(\d+)\s*<', content, re.I)
        episodes = int(match.group(1)) if match else None
        
        match = re.search(r'Genres:\s*</span>\s*(.+)\s*</div', content, re.I)
        genresHTML = match.group(1) if match else None
        soup = BeautifulSoup(genresHTML)
        genresA = soup.findAll('a')
        genres = []
        for a in genresA:
            genres.append(str(a.string))
        
        return {
            'title': title,
            'image': image,
            'score': score,
            'episodes': episodes,
            'genres': genres
        }
    else:
        data = json.loads(content)
        return {
            'title': data['title'],
            'image': data['image_url'],
            'score': data['members_score'],
            'episodes': data['episodes'],
            'genres': data['genres']
        }

def storeAnimeV1(id, data):
    memcache.set(id, data, 43200)
    q = db.GqlQuery('select * from AnimeV1 where id = :1', id)
    anime = q.get()
    
    # If genres is string, make it a list, just in case
    genres = data['genres']
    if genres is not None and isinstance(genres, str):
        genres = [genres]
    
    if not anime:
        anime = AnimeV1(
            id = id,
            title = data['title'],
            image = data['image'],
            score = data['score'],
            episodes = data['episodes'],
            genres = genres
        )
    else:
        anime.title = data['title']
        anime.image = data['image']
        anime.score = data['score']
        anime.episodes = data['episodes']
        anime.genres = genres
    anime.put()

app = webapp2.WSGIApplication([
        ('/', MainHandler),
        ('/v1/anime', AnimeV1Handler)
    ], debug=True)