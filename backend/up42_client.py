import time
import requests
import logging

logger = logging.getLogger(__name__)

class UP42Client:
    def __init__(self):
        self.auth_url = "https://auth.up42.com/realms/public/protocol/openid-connect/token"
        self.api_url = "https://api.up42.com"
        self.email = None
        self.password = None
        self.access_token = None
        self.token_expiry = 0
        self.token_type = "Bearer"

    def set_credentials(self, email, password):
        self.email = email
        self.password = password
        # Reset token to force new authentication
        self.access_token = None
        self.token_expiry = 0

    def get_token(self):
        """
        Retrieves the cached access token or requests a new one if expired or not available.
        """
        if not self.email or not self.password:
            raise ValueError("Credentials not set. Please authenticate first.")

        # Check if token is still valid (using a 15-second buffer)
        if self.access_token and time.time() < self.token_expiry - 15:
            return self.access_token

        logger.info("Access token expired or missing. Fetching a new one...")
        
        # Prepare OAuth2 request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "username": self.email,
            "password": self.password,
            "grant_type": "password",
            "client_id": "up42-api"
        }

        try:
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=10)
            if response.status_code != 200:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                raise Exception(f"Authentication failed (HTTP {response.status_code}): {response.text}")

            token_data = response.json()
            self.access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 300)
            self.token_expiry = time.time() + expires_in
            self.token_type = token_data.get("token_type", "Bearer")
            logger.info("Successfully authenticated with UP42.")
            return self.access_token
        except requests.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            raise Exception(f"Network error during authentication: {e}")

    def test_connection(self):
        """
        Tests if credentials can successfully retrieve a token.
        """
        try:
            token = self.get_token()
            return token is not None
        except Exception:
            return False

    def get_collections(self):
        """
        Fetches the list of geospatial collections from UP42.
        Passes the authentication token if available, otherwise queries publicly.
        """
        url = f"{self.api_url}/v2/collections?size=250"
        headers = {
            "accept": "application/json"
        }

        # Try to include token if user is authenticated
        if self.email and self.password:
            try:
                token = self.get_token()
                headers["Authorization"] = f"{self.token_type} {token}"
            except Exception as e:
                logger.warning(f"Could not use authentication token for collections list: {e}")

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                raise Exception(f"Failed to fetch collections (HTTP {response.status_code}): {response.text}")
            
            return response.json().get("content", [])
        except requests.RequestException as e:
            raise Exception(f"Error calling v2 collections API: {e}")

    def search_catalog(self, host_name, collections, geometry, datetime_str, limit=100, cloud_cover=None):
        """
        Searches the UP42 catalog for matching items using the STAC search endpoint.
        """
        token = self.get_token()
        url = f"{self.api_url}/catalog/hosts/{host_name}/stac/search"
        
        headers = {
            "Authorization": f"{self.token_type} {token}",
            "Content-Type": "application/json",
            "accept": "application/json"
        }

        # Construct request body
        body = {
            "collections": collections,
            "intersects": geometry,
            "limit": limit
        }

        if datetime_str:
            body["datetime"] = datetime_str

        # Add filters for cloud cover if specified (STAC extension query structure)
        # Note: Different hosts might support different property filters.
        # Standard STAC queries properties: e.g. eo:cloud_cover
        if cloud_cover is not None:
            # Cloud cover filter: <= cloud_cover
            body["query"] = {
                "eo:cloud_cover": {
                    "lte": cloud_cover
                }
            }

        logger.info(f"Sending search request to host '{host_name}' for collections {collections}...")
        try:
            response = requests.post(url, headers=headers, json=body, timeout=20)
            if response.status_code == 404:
                # Host not found or not supporting search
                logger.warning(f"Search API returned 404 for host: {host_name}")
                return {"type": "FeatureCollection", "features": [], "message": f"Host '{host_name}' search not supported or 404."}
            
            if response.status_code != 200:
                logger.error(f"Search request failed for host {host_name}: {response.status_code} - {response.text}")
                # Don't fail the whole search, just return empty with error message
                return {"type": "FeatureCollection", "features": [], "error": f"HTTP {response.status_code}: {response.text}"}

            return response.json()
        except requests.RequestException as e:
            logger.error(f"Request exception searching host {host_name}: {e}")
            return {"type": "FeatureCollection", "features": [], "error": str(e)}
