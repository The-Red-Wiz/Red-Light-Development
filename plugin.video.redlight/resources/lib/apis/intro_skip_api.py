# -*- coding: utf-8 -*-
import requests
from caches.main_cache import main_cache

THEINTRODB_URL = 'https://api.theintrodb.org/v3/media'
INTRODB_URL = 'https://api.introdb.app/segments'
_CACHE_HOURS = 168
_MIN_SEGMENT_SEC = 3
_MAX_SEGMENT_SEC = 600


def resolve_intro_segment(tmdb_id, imdb_id, season, episode, duration_sec=None):
	try:
		season, episode = int(season), int(episode)
	except:
		return None
	cache_key = 'intro_skip_%s_%s_%s_%s' % (tmdb_id, imdb_id or '', season, episode)
	cached = main_cache.get(cache_key)
	if cached is not None:
		return cached or None
	segment = None
	if tmdb_id not in (None, '', 'None', '0000000'):
		segment = _fetch_theintrodb(tmdb_id, season, episode, duration_sec)
	if not segment and imdb_id not in (None, '', 'None', 'tt0000000'):
		segment = _fetch_introdb(imdb_id, season, episode)
	main_cache.set(cache_key, segment or '', expiration=_CACHE_HOURS)
	return segment


def _valid_segment(start_sec, end_sec, duration_sec=None):
	try:
		start_sec, end_sec = float(start_sec), float(end_sec)
	except:
		return None
	if end_sec <= start_sec:
		return None
	length = end_sec - start_sec
	if length < _MIN_SEGMENT_SEC or length > _MAX_SEGMENT_SEC:
		return None
	if duration_sec:
		try:
			total = float(duration_sec)
			if total > 60 and end_sec > total:
				return None
		except:
			pass
	return {'start_sec': start_sec, 'end_sec': end_sec}


def _ms_segment(start_ms, end_ms, duration_sec=None):
	try:
		start_ms, end_ms = int(start_ms), int(end_ms)
	except:
		return None
	if end_ms <= start_ms:
		return None
	return _valid_segment(start_ms / 1000.0, end_ms / 1000.0, duration_sec)


def _fetch_theintrodb(tmdb_id, season, episode, duration_sec=None):
	try:
		params = {'tmdb_id': str(tmdb_id), 'season': season, 'episode': episode}
		if duration_sec:
			try:
				params['durationMs'] = int(float(duration_sec) * 1000)
			except:
				pass
		response = requests.get(THEINTRODB_URL, params=params, timeout=8)
		if response.status_code != 200:
			return None
		data = response.json()
		intro_list = data.get('intro') or []
		if not intro_list:
			return None
		entry = intro_list[0]
		segment = _ms_segment(entry.get('start_ms'), entry.get('end_ms'), duration_sec)
		if segment:
			segment['source'] = 'theintrodb'
		return segment
	except:
		return None


def _fetch_introdb(imdb_id, season, episode):
	try:
		params = {'imdb_id': str(imdb_id), 'season': season, 'episode': episode, 'segment_type': 'intro'}
		response = requests.get(INTRODB_URL, params=params, timeout=8)
		if response.status_code != 200:
			return None
		data = response.json()
		intro = data.get('intro')
		if not intro or not isinstance(intro, dict):
			return None
		start_sec = intro.get('start_sec', intro.get('start_ms'))
		end_sec = intro.get('end_sec', intro.get('end_ms'))
		if start_sec is not None and end_sec is not None:
			try:
				if float(start_sec) > 10000:
					start_sec = float(start_sec) / 1000.0
				if float(end_sec) > 10000:
					end_sec = float(end_sec) / 1000.0
			except:
				pass
		segment = _valid_segment(start_sec, end_sec)
		if segment:
			segment['source'] = 'introdb'
		return segment
	except:
		return None
