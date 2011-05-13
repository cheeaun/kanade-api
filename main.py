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
import re, cgi
from datetime import datetime, timedelta

from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util
from google.appengine.api import urlfetch, memcache
from django.utils import simplejson

MALAPI = 'http://mal-api.com/anime/'

class AnimeV1(db.Model):
    id = db.StringProperty(required=True)
    title = db.StringProperty(required=True)
    image = db.StringProperty(required=True)
    score = db.FloatProperty(required=True)
    episodes = db.IntegerProperty()
    genres = db.StringListProperty()
    updated_datetime = db.DateTimeProperty(auto_now=True)

class MainHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write('<!DOCTYPE html>\
<title>Kanade</title>\
<style>body{font-family: helvetica, arial, sans-serif; width: 320px; margin: 50px auto; font-size: 14px; line-height: 1.4em;}</style>\
<p>Hi there. I\'m Kanade.</p>\
<p>I am an API which gives you data of anime series with information such as scores, genres &amp; episode count. Here\'s a simple example: <a href="/v1/anime?id=21">/v1/anime?id=21</a></p>\
<p>I am powered by <a href="http://mal-api.com/">MyAnimeList Unofficial API</a>, <a href="http://myanimelist.net/">MyAnimeList</a> itself &amp; <a href="http://code.google.com/appengine/">Google App Engine</a>.</p>\
<p><a href="http://twitter.com/cheeaun">@cheeaun</a> &middot; <a href="http://github.com/cheeaun/kanade-api">GitHub</a></p>')

class AnimeV1Handler(webapp.RequestHandler):
    def get(self):
        id = cgi.escape(self.request.get('id'))
        callback = cgi.escape(self.request.get('callback'))
        
        response = {'ok': True, 'result': None}
        
        if re.match(r"^\d+$", id):
            content = memcache.get(id)
            if content is not None:
                response['result'] = content
            else:
                q = db.GqlQuery('select * from AnimeV1 where id = :1', id)
                result = q.get()
                if result is not None and (datetime.now() - result.updated_datetime <= timedelta(hours=24)):
                    content = {
                        'id': result.id,
                        'image': result.image,
                        'score': result.score,
                        'episodes': result.episodes,
                        'genres': result.genres
                    }
                    response['result'] = content
                else:
                    try:
                        result = urlfetch.fetch(MALAPI + id, deadline = 10)
                        if result.status_code == 200:
                            content = formatResponse(result.content)
                            response['result'] = content
                            storeAnimeV1(id, content)
                        else:
                            raise urlfetch.Error()
                    except urlfetch.Error:
                        # Try one more time before giving up
                        try:
                            result = urlfetch.fetch(MALAPI + id, deadline = 10)
                            if result.status_code == 200:
                                content = formatResponse(result.content)
                                response['result'] = content
                                storeAnimeV1(id, content)
                            else:
                                raise urlfetch.Error()
                        except urlfetch.Error:
                            response['ok'] = False
        else:
            response['ok'] = False
        
        json = simplejson.dumps(response, sort_keys=True)
        if callback and re.match(r'^[A-Za-z_$][A-Za-z0-9_$]*?$', callback): 
            json = callback + '(' + json + ')'
        
        if response['ok'] is True:
            self.response.headers['Cache-Control'] = 'public; max-age=43200'
        self.response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        self.response.headers['Vary'] = 'Accept-Encoding'
        self.response.headers['Proxy-Connection'] = 'Keep-Alive'
        self.response.headers['Connection'] = 'Keep-Alive'
        self.response.out.write(json)

def formatResponse(content):
    content = simplejson.loads(content)
    return {
        'title': content['title'],
        'image': content['image_url'],
        'score': content['members_score'],
        'episodes': content['episodes'],
        'genres': content['genres']
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

def main():
    application = webapp.WSGIApplication([
        ('/', MainHandler),
        ('/v1/anime', AnimeV1Handler)
    ], debug=True)
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
