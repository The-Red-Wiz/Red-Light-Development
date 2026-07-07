# -*- coding: utf-8 -*-
ENABLED = True

import json
import requests
from urllib.parse import urlencode
from caches.settings_cache import get_setting
from modules import kodi_utils
from modules.kodi_utils import logger

# id, short label, base URL (None = Custom; Custom is last in the picker)
PRESETS = (
	('0', 'Kuu', 'https://aiostreams.stremio.ru'),
	('1', 'Viren', 'https://aiostreams.viren070.me'),
	('2', 'Yeb', 'https://aiostreams.fortheweak.cloud'),
	('3', 'Midnight', 'https://aiostreamsfortheweebsstable.midnightignite.me'),
	('4', 'Custom', None),
)

INSTANCE_LABELS = {preset_id: label for preset_id, label, url in PRESETS}
INSTANCE_IDS = tuple(preset_id for preset_id, _, _ in PRESETS)
CUSTOM_INSTANCE_ID = '4'
PROFILE_SETTING = 'aiostreams.profiles'

PUBLIC_INSTANCES = tuple(url for _, _, url in PRESETS if url)
_PUBLIC_INDEX = {'0': 0, '1': 1, '2': 2, '3': 3}

def _empty_profile():
	return {'username': 'empty_setting', 'password': 'empty_setting', 'custom_url': ''}

def _load_profiles_raw():
	try:
		raw = get_setting('redlight.%s' % PROFILE_SETTING, '{}') or '{}'
		data = json.loads(raw)
		return data if isinstance(data, dict) else {}
	except: return {}

def _save_profiles(profiles):
	from caches.settings_cache import set_setting
	set_setting(PROFILE_SETTING, json.dumps(profiles))

def _ensure_profiles(profiles):
	for iid in INSTANCE_IDS:
		entry = profiles.get(iid)
		if not isinstance(entry, dict):
			profiles[iid] = _empty_profile()
			continue
		profiles[iid] = {
			'username': entry.get('username') or 'empty_setting',
			'password': entry.get('password') or 'empty_setting',
			'custom_url': (entry.get('custom_url') or '').strip(),
		}
	return profiles

def read_active_credentials():
	username = get_setting('redlight.aiostreams.username', 'empty_setting')
	password = get_setting('redlight.aiostreams.password', 'empty_setting')
	custom_url = (get_setting('redlight.aiostreams.custom_url', '') or '').strip()
	return {'username': username, 'password': password, 'custom_url': custom_url}

def _credentials_configured(credentials):
	return credentials['username'] not in ('empty_setting', '') or credentials['password'] not in ('empty_setting', '')

def _profiles_all_empty(profiles):
	for iid in INSTANCE_IDS:
		entry = profiles.get(iid, _empty_profile())
		if _credentials_configured(entry) or entry.get('custom_url'):
			return False
	return True

def ensure_profiles_initialized():
	profiles = _ensure_profiles(_load_profiles_raw())
	active = read_active_credentials()
	if _profiles_all_empty(profiles) and _credentials_configured(active):
		profiles[str(instance_id())] = dict(active)
		_save_profiles(profiles)
	return profiles

def persist_active_profile(instance_id_value=None):
	iid = str(instance_id_value if instance_id_value is not None else instance_id())
	profiles = _ensure_profiles(_load_profiles_raw())
	profiles[iid] = read_active_credentials()
	_save_profiles(profiles)

def apply_profile(instance_id_value):
	from caches.settings_cache import default_setting_values, property_safe_string, settings_cache
	profiles = _ensure_profiles(_load_profiles_raw())
	profile = profiles.get(str(instance_id_value), _empty_profile())
	for setting_id, value in (
		('aiostreams.username', profile['username']),
		('aiostreams.password', profile['password']),
		('aiostreams.custom_url', profile['custom_url']),
	):
		info = default_setting_values(setting_id)
		settings_cache.write_db(setting_id, value, info)
		try:
			settings_cache.set_memory_cache(setting_id, property_safe_string(value))
		except: pass

def instance_id():
	return str(get_setting('redlight.aiostreams.instance', '0'))

def base_url():
	current = instance_id()
	if current == CUSTOM_INSTANCE_ID:
		url = get_setting('redlight.aiostreams.custom_url', '').strip()
	else:
		index = _PUBLIC_INDEX.get(current, 0)
		url = PUBLIC_INSTANCES[index]
	return url.rstrip('/') if url else ''

def refresh_base_url_property():
	url = base_url()
	kodi_utils.set_property('redlight.aiostreams.base_url', url or '(not set — choose instance or enter Custom URL)')

def sync_instance_display_name():
	label = INSTANCE_LABELS.get(instance_id(), INSTANCE_LABELS['0'])
	kodi_utils.set_property('redlight.aiostreams.instance_name', label)

def active_instance_label():
	"""Short preset label for the instance used at scrape time (Kuu, Yeb, Midnight, Custom)."""
	return INSTANCE_LABELS.get(instance_id(), INSTANCE_LABELS['0'])

def instance_picker_list():
	"""Instance dropdown rows: alphabetical by preset name, Custom always last."""
	items = []
	for preset_id, label, url in PRESETS:
		if preset_id == CUSTOM_INSTANCE_ID:
			continue
		items.append((label.lower(), '%s — %s' % (label, url), preset_id))
	items.sort(key=lambda entry: entry[0])
	picker = [(display, preset_id) for _, display, preset_id in items]
	picker.append(('Custom — set URL below', CUSTOM_INSTANCE_ID))
	return picker

def refresh_settings_properties():
	kodi_utils.set_property('redlight.aiostreams.available', 'true' if ENABLED else 'false')
	ensure_profiles_initialized()
	sync_instance_display_name()
	refresh_base_url_property()

def auth():
	username = get_setting('redlight.aiostreams.username', 'empty_setting')
	password = get_setting('redlight.aiostreams.password', 'empty_setting')
	if username in ('empty_setting', '') or password in ('empty_setting', ''): return None
	return (username, password)

def flatten_result(raw):
	"""Merge parsedFile + top-level fields (Magneto player pattern)."""
	item = dict(raw)
	item.pop('sources', None)
	parsed = item.pop('parsedFile', None) or {}
	if not isinstance(parsed, dict): parsed = {}
	return {**parsed, **item}

def _norm_source_key(value):
	return str(value or '').strip().lower().replace(' ', '').replace('_', '').replace('.', '').replace('-', '')

_SERVICE_LABELS = (
	('realdebrid', 'RD', 'Real-Debrid', 'real-debrid'),
	('alldebrid', 'AD', 'AllDebrid', 'alldebrid'),
	('premiumize', 'PM', 'Premiumize', 'premiumize'),
	('torbox', 'TB', 'TorBox', 'torbox'),
	('offcloud', 'OC', 'Offcloud', 'offcloud'),
	('easynews', 'EN', 'EasyNews', 'easynews'),
	('easydebrid', 'ED', 'EasyDebrid', 'easydebrid'),
	('debrider', 'DR', 'Debrider', 'debrider'),
	('debridlink', 'DL', 'Debrid-Link', 'debridlink'),
	('putio', 'Putio', 'Putio', 'putio'),
	('pikpak', 'PK', 'PikPak', 'pikpak'),
	('seedr', 'Seedr', 'Seedr', 'seedr'),
	('nzbdav', 'NZB', 'NZBDav', 'nzbdav'),
	('altmount', 'Alt', 'AltMount', 'altmount'),
	('stremthru_newz', 'SNZ', 'StremThru', 'stremthru_newz'),
)

_ADDON_LABELS = (
	('torrentio', 'Torrentio', 'torrentio'),
	('comet', 'Comet', 'comet'),
	('mediafusion', 'MF', 'mediafusion'),
	('jackett', 'Jackett', 'jackett'),
	('prowlarr', 'Prowlarr', 'prowlarr'),
)

def _lookup_label(value, labels):
	key = _norm_source_key(value)
	for entry in labels:
		if key in (_norm_source_key(entry[0]), _norm_source_key(entry[3])):
			return entry[1], entry[2], entry[3]
	return None

def _label_from_url(url):
	try:
		from urllib.parse import urlparse
		host = (urlparse(url).netloc or '').lower()
	except: return None
	if not host: return None
	for token, short, name, icon in _SERVICE_LABELS + _ADDON_LABELS:
		if token in host.replace('-', '').replace('.', ''):
			return short, name, icon
	return None

def inner_source_display(merged):
	"""Return (panel_label, short, name, icon_key) for an AIOStreams result row."""
	service = merged.get('service')
	if isinstance(service, dict):
		service = service.get('id') or service.get('name')
	addon = merged.get('addon')
	if isinstance(addon, dict):
		addon = addon.get('name') or addon.get('id')
	indexer = merged.get('indexer')
	if service:
		match = _lookup_label(service, _SERVICE_LABELS)
		if match:
			short, name, icon = match
			return 'AIO / %s' % short, short, name, icon
		short = str(service).strip().upper()
		if len(short) > 8: short = short[:8]
		return 'AIO / %s' % short, short, str(service), 'aiostreams'
	if addon:
		match = _lookup_label(addon, _ADDON_LABELS)
		if match:
			short, name, icon = match
			return 'AIO / %s' % short, short, name, icon
		name = str(addon).strip()
		short = name if len(name) <= 10 else name[:10]
		return 'AIO / %s' % short, short, name, 'aiostreams'
	if indexer:
		name = str(indexer).strip()
		short = name if len(name) <= 10 else name[:10]
		return 'AIO / %s' % short, short, name, 'aiostreams'
	url_match = _label_from_url(merged.get('url') or merged.get('url_dl') or '')
	if url_match:
		short, name, icon = url_match
		return 'AIO / %s' % short, short, name, icon
	return 'AIO', 'AIO', 'AIOStreams', 'aiostreams'

_TRACKER_SITE_HINTS = (
	('torrentgalaxy', 'TorrentGalaxy'),
	('thepiratebay', 'The Pirate Bay'),
	('piratebay', 'The Pirate Bay'),
	('1337x', '1337x'),
	('rarbg', 'RARBG'),
	('yts', 'YTS'),
	('eztv', 'EZTV'),
	('kickasstorrents', 'KickassTorrents'),
	('limetorrents', 'LimeTorrents'),
	('nyaa', 'Nyaa'),
	('knaben', 'Knaben'),
	('torrentleech', 'TorrentLeech'),
	('iptorrents', 'IPTorrents'),
)

def _format_site_name(value):
	text = str(value or '').strip()
	if not text: return ''
	key = _norm_source_key(text)
	for token, display in _TRACKER_SITE_HINTS:
		if key == _norm_source_key(token) or _norm_source_key(token) in key:
			return display
	if text.islower() or '_' in text or '-' in text:
		return text.replace('_', ' ').replace('-', ' ').title()
	return text

def _site_from_tracker_entry(entry):
	if not entry: return ''
	text = str(entry).strip()
	if text.startswith(('udp:', 'wss:', 'ws:')): return ''
	try:
		from urllib.parse import urlparse
		if '://' in text:
			host = (urlparse(text).netloc or '').lower()
			if host.startswith('www.'): host = host[4:]
			host_key = host.replace('-', '').replace('.', '')
			for token, display in _TRACKER_SITE_HINTS:
				if token in host_key:
					return display
			parts = [p for p in host.split('.') if p and p not in ('com', 'org', 'net', 'to', 'me', 'io', 'cc', 'app')]
			if parts:
				return parts[0].title()
	except: pass
	if len(text) < 48 and '://' not in text:
		return _format_site_name(text)
	return ''

def origin_site_label(raw):
	"""Indexer / tracker site name for the Site row (TorrentGalaxy, etc.)."""
	indexer = raw.get('indexer')
	if indexer:
		site = _format_site_name(indexer)
		if site: return site
	sources = raw.get('sources')
	if isinstance(sources, list):
		for entry in sources:
			site = _site_from_tracker_entry(entry)
			if site: return site
	addon = raw.get('addon')
	if isinstance(addon, dict): addon = addon.get('name') or addon.get('id')
	if addon and not raw.get('service'):
		return _format_site_name(addon) or str(addon).strip()
	return ''

def hoster_label(raw):
	"""Hoster row label for AIOStreams results."""
	cached = raw.get('cached')
	stream_type = str(raw.get('type') or '').lower()
	if cached is True:
		return '[B]CACHED[/B]'
	if cached is False:
		return 'UNCACHED'
	if stream_type in ('usenet', 'stremio-usenet') or raw.get('nzbUrl'):
		return 'USENET'
	if stream_type == 'p2p' or raw.get('infoHash'):
		return 'TORRENT'
	return 'DIRECT'

def playback_headers(item):
	headers = item.get('request_headers') or item.get('requestHeaders')
	return headers if isinstance(headers, dict) and headers else None

def _format_payload_entries(items):
	lines = []
	for item in items or ():
		if not isinstance(item, dict):
			lines.append(str(item))
			continue
		title = item.get('title') or item.get('name') or 'entry'
		desc = item.get('description') or item.get('message') or ''
		lines.append('%s: %s' % (title, desc) if desc else str(title))
	return lines

def _log_http_error(response, search_link):
	try:
		body = response.json()
		err = body.get('error')
		if isinstance(err, dict):
			logger('aiostreams API', 'HTTP %s | %s: %s | %s' % (
				response.status_code, err.get('code', ''), err.get('message', ''), response.url))
			return
		if isinstance(err, str) and err.strip():
			logger('aiostreams API', 'HTTP %s | %s | %s' % (response.status_code, err.strip(), response.url))
			return
		detail = body.get('detail')
		if detail:
			logger('aiostreams API', 'HTTP %s | %s | %s' % (response.status_code, detail, response.url))
			return
		if body.get('success') is False:
			logger('aiostreams API', 'HTTP %s | success=false | %s' % (response.status_code, response.url))
			return
	except: pass
	logger('aiostreams API', 'HTTP %s | %s' % (response.status_code, getattr(response, 'url', search_link)))

def _log_search_response(response, payload, results):
	elapsed = response.elapsed.total_seconds()
	filtered = payload.get('filtered', 0) or 0
	errors = payload.get('errors') or []
	statistics = payload.get('statistics') or []
	logger('aiostreams API', '%.3fs | %s results | filtered=%s | %s' % (elapsed, len(results), filtered, response.url))
	for line in _format_payload_entries(errors):
		logger('aiostreams API', 'source error: %s' % line)
	for line in _format_payload_entries(statistics):
		logger('aiostreams API', 'statistic: %s' % line)
	if not results and filtered:
		logger('aiostreams API', 'all streams removed by instance filters (filtered=%s)' % filtered)
	if not results and not errors and not statistics:
		logger('aiostreams API', 'empty payload — instance returned no results, errors, or statistics')

def _parse_api_errors(payload):
	return [': '.join(str(v) for v in i.values()) for i in payload.get('errors', []) if isinstance(i, dict)]

def search(media_type, imdb_id, season=None, episode=None, timeout=30):
	credentials = auth()
	if not credentials:
		logger('aiostreams API', 'search skipped — username/password not configured')
		return [], ['AIOStreams username/password not configured']
	if not imdb_id:
		logger('aiostreams API', 'search skipped — missing IMDb id')
		return [], ['Missing IMDb id for AIOStreams search']
	base = base_url()
	if not base:
		logger('aiostreams API', 'search skipped — no instance URL configured')
		return [], ['No AIOStreams instance URL configured']
	if media_type == 'movie':
		params = {'type': 'movie', 'id': imdb_id}
	else:
		params = {'type': 'series', 'id': '%s:%s:%s' % (imdb_id, season, episode)}
	search_link = '%s/api/v1/search' % base
	try:
		response = requests.get(search_link, params=params, auth=credentials, timeout=timeout)
		if not response.ok:
			_log_http_error(response, search_link)
			response.raise_for_status()
		body = response.json()
		if body.get('success') is False:
			err = body.get('error') or {}
			if isinstance(err, dict):
				logger('aiostreams API', 'success=false | %s: %s | %s' % (
					err.get('code', ''), err.get('message', ''), response.url))
			elif isinstance(err, str) and err.strip():
				logger('aiostreams API', 'success=false | %s | %s' % (err.strip(), response.url))
		payload = body.get('data', {}) or {}
		results = payload.get('results', []) or []
		errors = _parse_api_errors(payload)
		_log_search_response(response, payload, results)
		return results, errors
	except requests.exceptions.RequestException as e:
		logger('aiostreams API', '%s\n%s' % (e, getattr(getattr(e, 'request', None), 'url', search_link)))
		return [], []

def resolve_playback_url(item):
	url = item.get('url_dl') or item.get('url')
	if not url: return None
	headers = playback_headers(item)
	if headers: return '%s|%s' % (url, urlencode(headers))
	return url
