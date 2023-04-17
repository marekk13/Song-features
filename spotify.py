from dotenv import load_dotenv
import os
import base64
import asyncio
import aiohttp
import json
import time
from itertools import chain
from math import exp
import sys

load_dotenv() #loading environment variable file
#getting environment variables
client_id=os.getenv("CLIENT_ID")
client_secret=os.getenv("CLIENT_SECRET")


class MusicData():  
    @classmethod
    async def create(cls, *artists):
        self=MusicData()
        self.req_count=0
        timeout = aiohttp.ClientTimeout(total=600)
        """1. Uzyskanie tokena"""
        self.token=await self.get_token()

        #async with aiohttp.ClientSession() as session:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            """2. Uzyskanie ID podanych artystów"""
            artists_list=list(artists)
            url="https://api.spotify.com/v1/search"
            query="?q={}&type=artist&limit=1"
            #zebranie zadań (requesty do uzyskania id rozważanych artystów)
            tasks_artists=self.get_tasks(session, artists_list, url, query)

            #czekamy, az zbierzemy wszystkie odpowiedzi
            artists_responses=await asyncio.gather(*tasks_artists) #lista obiektów typu ClientResponse

            #dla kazdej odpowiedzi wydobywamy id i dodajemy do listy id artystów
            print("Sprawdzanie statusów odpowiedzi przy endpoincie search for item: ")
            if await self.response_check(artists_responses, tasks_artists):
                print("Ok!")
                self.artists_ids=[]
                for i, response in enumerate(artists_responses):
                    json_result = await response.json() #nie możemy działać na obiekcie asynchronicznym bez odczekania await lub asyncio.ensure_future()
                    if json_result["artists"]["items"]:
                        self.artists_ids.append(json_result["artists"]["items"][0]['id'])
                    else:
                        print(f"Artysta {artists[i]} nie został znaleziony\n")
                if len(self.artists_ids)==0:
                    sys.exit("Nie znaleziono żadnych z podanych artystów!")
            else:
                sys.exit("Wychodzenie z programu przez brak pożądanej odpowiedzi od API")

            print()
            """3. Uzyskanie ID wszystkich albumów i singli podanych artystów"""
            url="https://api.spotify.com/v1/artists/"
            query="{}/albums?include_groups=single,album"
            tasks_albums=self.get_tasks(session, self.artists_ids, url, query)
            albums_responses=await asyncio.gather(*tasks_albums)
            print("Sprawdzanie statusów odpowiedzi przy endpoincie get artist's albums: ")
            if await self.response_check(albums_responses, tasks_albums):
                print("Ok!")
                self.albums_ids=[]
                for response in albums_responses:
                    json_result = await response.json()
                    for album in json_result['items']:
                        self.albums_ids.append(album['id']) 
            else:
                sys.exit("Wychodzenie z programu przez brak pożądanej odpowiedzi od API")

            print()
            """4. Uzyskanie ID wszystkich piosenek"""
            url="https://api.spotify.com/v1/albums/"
            query="{}/tracks?limit=50"
            tasks_songs=self.get_tasks(session, self.albums_ids, url, query)
            songs_responses=await asyncio.gather(*tasks_songs)
            self.songs_ids=[]
            print("Sprawdzanie statusów odpowiedzi przy endpoincie get several albums: ")
            if await self.response_check(songs_responses, tasks_songs):
                print("Ok!")
                for response in songs_responses:
                    json_result = await response.json()
                    for song in json_result['items']:
                        self.songs_ids.append(song['id']) 
            else:
                sys.exit("Wychodzenie z programu przez brak pożądanej odpowiedzi od API")
            print()

            """5. Uzyskanie informacji o piosenkach"""
            url="https://api.spotify.com/v1/tracks/"
            query="?ids={}"

            #w tym endpoincie maksymalnie 50 id oddzielonych przecinkami (get several tracks)
            idcommas=list(self.divide_chunks(self.songs_ids, 50))

            #tasks_songs_info = list(chain.from_iterable([self.get_tasks(session, idlist, url, query) for idlist in idlists]))
            tasks_songs_info=self.get_tasks(session, idcommas, url, query)

            songs_info_responses=await asyncio.gather(*tasks_songs_info)
            print("Sprawdzanie statusów odpowiedzi przy endpoincie get several tracks: ")
            if await self.response_check(songs_info_responses, tasks_songs_info):
                print("Ok!")
                self.values=[] #przyszle wartosci w slowniku
                for response in songs_info_responses:
                    json_result = await response.json()
                    for track in json_result["tracks"]:
                        self.values.append([track["artists"][0]["name"], track["id"], track["name"], track["popularity"],  track["album"]["album_group"],  #ew track["album"]["album_type"]
                                            track["album"]["name"], track["album"]["release_date"], track["album"]["release_date_precision"], track["explicit"]])
            else:
                sys.exit("Wychodzenie z programu przez brak pożądanej odpowiedzi od API")
            print()

            #max 100 id oddzielonych przecinkami (get tracks' audio features)
            url="https://api.spotify.com/v1/audio-features/"
            query="?ids={}"
            idcommas=list(self.divide_chunks(idcommas, 2))
            tasks_songs_info2=self.get_tasks(session, idcommas, url, query)
            songs_info_responses2=await asyncio.gather(*tasks_songs_info2)
            print("Sprawdzanie statusów odpowiedzi przy endpoincie audio features: ")
            if await self.response_check(songs_info_responses2, tasks_songs_info2):
                print("Ok!")
                it=0
                for response in songs_info_responses2:
                    json_result = await response.json()
                    for track in json_result["audio_features"]:
                        try:
                            self.values[it]=list(chain(self.values[it],[track["acousticness"], track["danceability"], track["energy"], 
                                                track["instrumentalness"], track["liveness"], track["loudness"], track["speechiness"], track["tempo"], track["valence"]]))
                        except TypeError:
                            self.values[it]=list(chain(self.values[it], [None]*9))
                        it+=1
            else:
                sys.exit("Wychodzenie z programu przez brak pożądanej odpowiedzi od API")

            headers=["artist_name", "song_id", "song_name","popularity","type","album_name","release_date","release_date_precision","explicit",
                     "acousticness","danceability","energy","instrumentalness","liveness","loudness", "speechiness", "tempo", "valence"]
            self.data=[]
            for song in self.values:
                self.data.append(dict(zip(headers, song))) 
            i=0
            print(f"Znaleziono {len(self.data)} piosenek")
        return self

    def divide_chunks(self, l, n):
        for i in range(0, len(l), n):
            yield ",".join(l[i:i + n])

    def get_tasks(self, session, elements, url, query):
        headers = self.get_auth_header()
        tasks=[]
        for element in elements:
            query_url=url+query.format(element)
            self.req_count+=1
            tasks.append(asyncio.create_task(session.get(query_url, headers=headers)))
        return tasks
    

        
    async def response_check(self, responses, tasks):
        #jesli kod 200 to zwracamy true
        for i,response in enumerate(responses):
            if response.status==403:
                print("Bad OAuth request "+f"iteration {i}")
                return False
            elif response.status==429:
                tasks=tasks[i:]
                print("Za dużo requestów "+f"iteracja {i}")
                break
            elif response.status==400: #np invalid id
                print("Niewłaściwy URL/query "+f"iteracja {i}")
                return False
            elif response.status!=200:
                print("Nieznany błąd "+f"iteracja {i}")
                return False
        else: #brak innych kodów niż 200
            return True
        j=0
        while j<4:
            waiting_time=exp(j)
            print(f"Ponowna próba po {waiting_time:.2f}s oczekiwania")
            await asyncio.sleep(waiting_time) #exponential backoff
            responses[i:]=await asyncio.gather(*tasks)
            print([response.status for response in responses])
            if all(response.status == 200 for response in responses):
                return True
            j+=1
        return False


    #uzyskanie tokena
    async def get_token(self):
        auth_string=client_id+":"+client_secret #wymaganie spotify
        auth_bytes=auth_string.encode("utf-8")

        #wymagane kodowanie do base64
        auth_base64=str(base64.b64encode(auth_bytes), "utf-8")

        url="https://accounts.spotify.com/api/token"

        #tworzenie nagłówków
        headers={
            "Authorization": "Basic " + auth_base64,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data={"grant_type": "client_credentials"} 

        #post request do spotify
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as result:
                json_result=json.loads(await result.read())
                token=json_result["access_token"]
        self.req_count+=1
        return token
        

    #uzyskanie nagłówka do autoryzacji
    def get_auth_header(self):
        return {"Authorization": "Bearer " + self.token}
    
def validate(s):
    s=s.strip().split(",")
    if len(s) > 6:
        sys.exit("Podano zbyt wielu artystów")
    else:
        return [el.strip() for el in s]
    
async def main():
    artists=validate(input("Podaj maksymalnie sześciu artystów, których chcesz wyszukać. Oddzielaj ich przecinkami: "))
    start=time.time()
    a=await MusicData.create(*artists) 
    end=time.time() 
    print(f"Działanie programu przy {a.req_count} requestach zajęło {end-start:.2f}")


if __name__=="__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())