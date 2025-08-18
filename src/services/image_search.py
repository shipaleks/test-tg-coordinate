"""
New image search system focused on fact relevance.
"""

import aiohttp
import asyncio
import logging
import re
from typing import List, Tuple, Optional, Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ImageSearchEngine:
    """Enhanced image search with multiple strategies for fact-relevant images."""
    
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def search_images(
        self,
        fact_text: str,
        place_name: str,
        coordinates: Tuple[float, float],
        sources: List[Tuple[str, str]],
        max_images: int = 5
    ) -> List[str]:
        """
        Search for images relevant to the fact.
        
        Args:
            fact_text: The full fact text
            place_name: The location/place name from the fact
            coordinates: (lat, lon) tuple of the POI
            sources: List of (title, url) tuples from fact sources
            max_images: Maximum number of images to return (1-9)
            
        Returns:
            List of image URLs
        """
        # Extract key entities from fact text
        entities = self._extract_entities(fact_text, place_name)
        
        # Run multiple search strategies in parallel
        tasks = []
        
        # Strategy 1: Search for specific entities mentioned in the fact
        if entities['people']:
            for person in entities['people'][:2]:  # Limit to avoid too many requests
                tasks.append(self._search_person_images(person))
                
        if entities['buildings']:
            for building in entities['buildings'][:2]:
                tasks.append(self._search_building_images(building, coordinates))
                
        # Strategy 2: Extract images from source URLs if they're Wikimedia
        if sources:
            tasks.append(self._extract_images_from_sources(sources))
            
        # Strategy 3: Search by specific place name
        if place_name:
            tasks.append(self._search_place_images(place_name, coordinates))
            
        # Strategy 4: Geosearch around coordinates as fallback
        tasks.append(self._geosearch_commons(coordinates, radius=200))
        
        # Execute all strategies
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect and deduplicate results
        all_images = []
        seen_urls = set()
        
        for result in all_results:
            if isinstance(result, Exception):
                logger.debug(f"Search strategy failed: {result}")
                continue
            if result:
                for img in result:
                    if img and img not in seen_urls:
                        seen_urls.add(img)
                        all_images.append(img)
                        
        # Filter and rank images
        ranked_images = self._rank_images(all_images, fact_text, place_name, max_images)
        
        return ranked_images[:max_images]
        
    def _extract_entities(self, fact_text: str, place_name: str) -> Dict[str, List[str]]:
        """Extract relevant entities from fact text."""
        entities = {
            'people': [],
            'buildings': [],
            'streets': [],
            'landmarks': []
        }
        
        # Extract people names (capitalized words that might be names)
        # Simple heuristic: consecutive capitalized words
        name_pattern = r'\b[A-ZА-Я][a-zа-я]+(?:\s+[A-ZА-Я][a-zа-я]+)+\b'
        potential_names = re.findall(name_pattern, fact_text)
        
        # Filter out common non-name phrases
        non_names = {'Paris France', 'Rue de', 'Boulevard', 'Avenue', 'Place', 'Square'}
        entities['people'] = [
            name for name in potential_names 
            if not any(nn in name for nn in non_names)
        ][:3]  # Limit to 3 most likely names
        
        # Extract building/landmark mentions
        building_keywords = [
            'церковь', 'église', 'church',
            'собор', 'cathédrale', 'cathedral',
            'дворец', 'palais', 'palace',
            'замок', 'château', 'castle',
            'музей', 'musée', 'museum',
            'театр', 'théâtre', 'theater',
            'башня', 'tour', 'tower',
            'арка', 'arc', 'arch',
            'мост', 'pont', 'bridge',
            'вокзал', 'gare', 'station',
            'рынок', 'marché', 'market',
            'парк', 'parc', 'park',
            'сад', 'jardin', 'garden',
            'фонтан', 'fontaine', 'fountain',
            'статуя', 'statue', 'statue',
            'памятник', 'monument', 'monument',
            'мемориал', 'mémorial', 'memorial'
        ]
        
        fact_lower = fact_text.lower()
        for keyword in building_keywords:
            if keyword in fact_lower:
                # Try to extract the full name around the keyword
                pattern = rf'(\w+\s+)?{keyword}(\s+\w+)?'
                matches = re.finditer(pattern, fact_lower, re.IGNORECASE)
                for match in matches:
                    building_name = match.group().strip()
                    if len(building_name) > len(keyword):  # Only if we found more than just the keyword
                        entities['buildings'].append(building_name)
                        
        # Add the place name itself as a building/landmark
        if place_name and len(place_name) > 5:
            entities['buildings'].insert(0, place_name)
            
        return entities
        
    async def _search_person_images(self, person_name: str) -> List[str]:
        """Search for images of a specific person."""
        try:
            # Search on Commons for the person
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': person_name,
                'srnamespace': '6',  # File namespace
                'srlimit': '5'
            }
            
            url = 'https://commons.wikimedia.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            images = []
            for item in data.get('query', {}).get('search', []):
                title = item.get('title', '')
                if title.startswith('File:'):
                    # Get the actual image URL
                    img_url = await self._get_image_url(title)
                    if img_url:
                        images.append(img_url)
                        
            return images[:3]
        except Exception as e:
            logger.debug(f"Person image search failed for {person_name}: {e}")
            return []
            
    async def _search_building_images(self, building_name: str, coordinates: Tuple[float, float]) -> List[str]:
        """Search for images of a specific building or landmark."""
        try:
            # First try exact name search on Commons
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': f'"{building_name}"',  # Exact phrase
                'srnamespace': '6',  # File namespace
                'srlimit': '10'
            }
            
            url = 'https://commons.wikimedia.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            images = []
            for item in data.get('query', {}).get('search', []):
                title = item.get('title', '')
                if title.startswith('File:'):
                    # Filter out logos, maps, etc
                    title_lower = title.lower()
                    if any(skip in title_lower for skip in ['logo', 'map', 'plan', 'carte', 'схема']):
                        continue
                    
                    img_url = await self._get_image_url(title)
                    if img_url:
                        images.append(img_url)
                        
            return images[:4]
        except Exception as e:
            logger.debug(f"Building image search failed for {building_name}: {e}")
            return []
            
    async def _search_place_images(self, place_name: str, coordinates: Tuple[float, float]) -> List[str]:
        """Search for images of a specific place."""
        try:
            # Clean place name for search
            clean_name = re.sub(r'\([^)]*\)', '', place_name).strip()
            clean_name = re.sub(r',.*', '', clean_name).strip()
            
            # Search on Commons
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': clean_name,
                'srnamespace': '6',  # File namespace
                'srlimit': '15'
            }
            
            url = 'https://commons.wikimedia.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            images = []
            for item in data.get('query', {}).get('search', []):
                title = item.get('title', '')
                if title.startswith('File:'):
                    # Filter out non-photo content
                    title_lower = title.lower()
                    if any(skip in title_lower for skip in [
                        'logo', 'map', 'plan', 'carte', 'схема', 'diagram', 
                        'chart', 'graph', 'coat_of_arms', 'flag', 'emblem',
                        'seal', 'badge', 'icon', 'symbol'
                    ]):
                        continue
                        
                    img_url = await self._get_image_url(title)
                    if img_url:
                        images.append(img_url)
                        
            return images[:6]
        except Exception as e:
            logger.debug(f"Place image search failed for {place_name}: {e}")
            return []
            
    async def _extract_images_from_sources(self, sources: List[Tuple[str, str]]) -> List[str]:
        """Extract images directly from Wikimedia source URLs."""
        images = []
        
        for title, url in sources:
            if 'wikidata.org' in url and '/wiki/Q' in url:
                # Extract QID and get P18 image
                qid_match = re.search(r'/wiki/(Q\d+)', url)
                if qid_match:
                    qid = qid_match.group(1)
                    img = await self._get_wikidata_image(qid)
                    if img:
                        images.append(img)
                        
            elif 'commons.wikimedia.org' in url and '/wiki/File:' in url:
                # Direct Commons file
                file_match = re.search(r'/wiki/(File:[^#]+)', url)
                if file_match:
                    file_name = file_match.group(1)
                    img_url = await self._get_image_url(file_name)
                    if img_url:
                        images.append(img_url)
                        
        return images
        
    async def _geosearch_commons(self, coordinates: Tuple[float, float], radius: int = 200) -> List[str]:
        """Search Commons for images near coordinates."""
        try:
            lat, lon = coordinates
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'geosearch',
                'gscoord': f'{lat}|{lon}',
                'gsradius': radius,
                'gslimit': '20',
                'gsnamespace': '6'  # File namespace
            }
            
            url = 'https://commons.wikimedia.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            images = []
            for item in data.get('query', {}).get('geosearch', []):
                title = item.get('title', '')
                if title.startswith('File:'):
                    # Skip generic files
                    title_lower = title.lower()
                    if any(skip in title_lower for skip in [
                        'logo', 'map', 'plan', 'carte', 'схема', 'flag',
                        'coat_of_arms', 'emblem', 'seal', 'badge'
                    ]):
                        continue
                        
                    img_url = await self._get_image_url(title)
                    if img_url:
                        images.append(img_url)
                        
            return images[:10]
        except Exception as e:
            logger.debug(f"Commons geosearch failed: {e}")
            return []
            
    async def _get_wikidata_image(self, qid: str) -> Optional[str]:
        """Get P18 (image) property from Wikidata entity."""
        try:
            params = {
                'action': 'wbgetentities',
                'format': 'json',
                'ids': qid,
                'props': 'claims'
            }
            
            url = 'https://www.wikidata.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            entity = data.get('entities', {}).get(qid, {})
            claims = entity.get('claims', {})
            p18 = claims.get('P18', [])
            
            if p18 and p18[0].get('mainsnak', {}).get('datavalue'):
                filename = p18[0]['mainsnak']['datavalue']['value']
                return await self._get_image_url(f'File:{filename}')
                
        except Exception as e:
            logger.debug(f"Wikidata image fetch failed for {qid}: {e}")
            
        return None
        
    async def _get_image_url(self, file_title: str, width: int = 1600) -> Optional[str]:
        """Convert Commons file title to direct image URL."""
        try:
            params = {
                'action': 'query',
                'format': 'json',
                'prop': 'imageinfo',
                'titles': file_title,
                'iiprop': 'url|size|mime',
                'iiurlwidth': str(width)
            }
            
            url = 'https://commons.wikimedia.org/w/api.php'
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
            pages = data.get('query', {}).get('pages', {})
            for page in pages.values():
                imageinfo = page.get('imageinfo', [])
                if imageinfo:
                    info = imageinfo[0]
                    # Prefer thumbnail URL for consistent sizing
                    img_url = info.get('thumburl') or info.get('url')
                    if img_url:
                        return img_url
                        
        except Exception as e:
            logger.debug(f"Image URL fetch failed for {file_title}: {e}")
            
        return None
        
    def _rank_images(self, images: List[str], fact_text: str, place_name: str, max_count: int) -> List[str]:
        """Rank images by relevance to the fact."""
        if len(images) <= max_count:
            return images
            
        # For now, just take the first max_count images
        # In the future, could implement more sophisticated ranking
        return images[:max_count]
