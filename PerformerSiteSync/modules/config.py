"""
Configuration Management Module
Handles loading and managing Stash configuration and plugin settings
"""

import stashapi.log as log
from stashapi.stashapp import StashInterface
from typing import Dict, List, Optional, Any
import os
import yaml
from pathlib import Path


class ConfigManager:
    """Manages configuration loading and validation for the plugin"""
    
    def __init__(self, server_connection=None):
        # Initialize StashInterface with proper connection configuration
        if server_connection:
            # Use the server connection provided by Stash (preferred method)
            log.info("Using server connection provided by Stash")
            log.debug(f"Server connection keys: {list(server_connection.keys()) if isinstance(server_connection, dict) else 'Not a dict'}")
            log.debug(f"Server connection content: {dict((k, v[:10] + '...' if k in ['ApiKey', 'apikey', 'api_key'] and isinstance(v, str) else v) for k, v in server_connection.items()) if isinstance(server_connection, dict) else server_connection}")
            
            try:
                self.stash = StashInterface(server_connection)
                log.info("StashInterface initialized successfully with server connection")
                
                # Test the connection immediately like TPDBMarkers does
                log.info("Testing connection by calling get_configuration...")
                test_config = self.stash.get_configuration()
                log.info("Successfully retrieved configuration from Stash")
                
                # Debug: Show what we got from the configuration
                log.info(f"Configuration keys: {list(test_config.keys()) if test_config else 'None'}")
                if test_config and 'general' in test_config:
                    general_keys = list(test_config['general'].keys()) if test_config['general'] else []
                    log.info(f"General config keys: {general_keys}")
                    if 'stashBoxes' in test_config['general']:
                        stash_boxes = test_config['general']['stashBoxes']
                        log.info(f"Found {len(stash_boxes)} stash boxes configured")
                        for i, box in enumerate(stash_boxes):
                            box_info = {k: (v[:10] + '...' if k == 'apikey' and v else v) for k, v in box.items()}
                            log.info(f"Stash box {i}: {box_info}")
                
                # Debug: Check plugins configuration  
                if test_config and 'plugins' in test_config:
                    plugins_config = test_config['plugins']
                    log.info(f"Plugins config keys: {list(plugins_config.keys()) if plugins_config else 'None'}")
                    if 'performer_site_sync' in plugins_config:
                        log.info(f"Found performer_site_sync config: {plugins_config['performer_site_sync']}")
                
            except Exception as e:
                log.error(f"Failed to initialize StashInterface with server connection: {e}")
                log.info("Falling back to manual config reading...")
                # Fallback to manual config reading
                stash_conn = self._get_stash_connection_config()
                self.stash = StashInterface(stash_conn)
        else:
            # Fallback to reading config manually (for standalone testing)
            log.warning("No server connection provided, attempting manual config reading")
            stash_conn = self._get_stash_connection_config()
            log.info(f"Initializing StashInterface with connection: {dict((k, v[:10] + '...' if k == 'ApiKey' else v) for k, v in stash_conn.items())}")
            
            try:
                self.stash = StashInterface(stash_conn)
                log.info("StashInterface initialized successfully")
            except Exception as e:
                log.error(f"Failed to initialize StashInterface: {e}")
                # Try without API key to see if that's the issue
                log.info("Attempting connection without API key for debugging...")
                stash_conn_no_key = {k: v for k, v in stash_conn.items() if k != 'ApiKey'}
                try:
                    self.stash = StashInterface(stash_conn_no_key)
                    log.warning("Connection successful WITHOUT API key - this suggests API key format issue")
                except Exception as e2:
                    log.error(f"Connection also fails without API key: {e2}")
                raise e
            
        self._plugin_config = None
        self._endpoints = None
        self._sources = None
        
    def _get_stash_connection_config(self) -> Dict[str, Any]:
        """Get Stash connection configuration including API key from config.yml"""
        try:
            # Try to find the Stash config.yml file
            # Common locations for Stash config
            config_paths = [
                Path.home() / ".stash" / "config.yml",  # Default location
                Path("/root/.stash/config.yml"),        # Docker location
                Path("D:/config.yml"),                  # User's specific location
                Path("/config/config.yml"),             # Another Docker location
            ]
            
            config_data = None
            config_file = None
            
            for config_path in config_paths:
                if config_path.exists():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f)
                        config_file = config_path
                        log.debug(f"Found Stash config at: {config_path}")
                        break
                    except Exception as e:
                        log.debug(f"Could not read config from {config_path}: {e}")
                        continue
            
            # Build connection configuration
            stash_conn = {
                "Logger": log,
                "Host": "localhost",
                "Port": 9999,
                "Scheme": "http"
            }
            
            if not config_data:
                log.warning("Could not find or read Stash config.yml, using default connection settings (no API key)")
                return stash_conn
            
            # Extract settings from config
            api_key = config_data.get('api_key')
            host = config_data.get('host', 'localhost')
            port = config_data.get('port', 9999)
            
            # Update connection with actual values
            if host == '0.0.0.0':
                host = 'localhost'  # Convert 0.0.0.0 to localhost for client connections
                
            stash_conn.update({
                "Host": host,
                "Port": port
            })
                
            if api_key:
                stash_conn["ApiKey"] = api_key
                log.info(f"Using API key from config: {api_key[:10]}...")
                log.debug(f"Full connection config: {dict((k, v[:10] + '...' if k == 'ApiKey' else v) for k, v in stash_conn.items())}")
            else:
                log.warning("No API key found in config.yml - connection may fail if Stash requires authentication")
                
            log.info(f"Configured Stash connection: {stash_conn['Scheme']}://{stash_conn['Host']}:{stash_conn['Port']}")
            return stash_conn
            
        except Exception as e:
            log.error(f"Error reading Stash configuration: {e}")
            # Return default configuration with logger
            return {
                "Logger": log,
                "Host": "localhost", 
                "Port": 9999,
                "Scheme": "http"
            }
        
    @property
    def plugin_config(self) -> Dict[str, Any]:
        """Get plugin configuration, loading if necessary"""
        if self._plugin_config is None:
            log.info("Loading plugin_config property...")
            self._plugin_config = self._load_plugin_config()
            log.info("plugin_config property loaded successfully")
        return self._plugin_config
    
    @property
    def endpoints(self) -> Dict[str, Dict[str, str]]:
        """Get endpoint configuration, loading if necessary"""
        if self._endpoints is None:
            log.info("Loading endpoints property...")
            self._endpoints = self._load_stash_configuration()
            log.info("endpoints property loaded successfully")
        return self._endpoints
    
    @property
    def sources(self) -> Dict[str, Dict[str, Any]]:
        """Get sources configuration, loading if necessary"""
        if self._sources is None:
            log.info("Loading sources property...")
            self._sources = self._build_sources_config()
            log.info("sources property loaded successfully")
        return self._sources

    def _load_plugin_config(self) -> Dict[str, Any]:
        """Load plugin configuration from Stash settings"""
        try:
            log.info("Loading plugin configuration from Stash...")
            config = self.stash.get_configuration()
            log.info("Retrieved configuration successfully in _load_plugin_config")
            
            plugin_config = config.get("plugins", {})
            log.info(f"Plugin config section: {list(plugin_config.keys()) if plugin_config else 'Empty'}")
            
            performer_sync_config = plugin_config.get("PerformerSiteSync", {})
            log.info(f"PerformerSiteSync config: {performer_sync_config}")
            
            # Also check alternative key names
            alt_config = plugin_config.get("performer_site_sync", {})
            if alt_config:
                log.info(f"Found performer_site_sync config: {alt_config}")
                performer_sync_config.update(alt_config)
            
            # Default configuration
            default_config = {
                "cacheExpirationHours": 24,
                "rateLimit": 2,
                "enableStashDB": True,
                "enableTPDB": True,
                "enableFansDB": True,
                "sourcePrecedence": "stashdb,tpdb,fansdb",
                "debugLogging": False,
                "performerImageUpdate": True,
                "enableNameSearch": True,  # New setting for name-based searches
                "autoCreateSites": False   # New setting for site auto-creation
            }
            
            # Merge with user configuration
            config = {**default_config, **performer_sync_config}
            log.info(f"Final merged plugin config: {config}")
            
            if config["debugLogging"]:
                log.info(f"Loaded plugin configuration: {config}")
                
            return config
            
        except Exception as e:
            log.error(f"Failed to load plugin configuration: {e}")
            log.error(f"Exception type: {type(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return {
                "cacheExpirationHours": 24,
                "rateLimit": 2,
                "enableStashDB": True,
                "enableTPDB": True,
                "enableFansDB": True,
                "sourcePrecedence": "stashdb,tpdb,fansdb",
                "debugLogging": False,
                "performerImageUpdate": True,
                "enableNameSearch": True,
                "autoCreateSites": False
            }

    def _load_stash_configuration(self) -> Dict[str, Dict[str, str]]:
        """Load endpoint configuration from Stash's stash_boxes configuration"""
        try:
            log.info("Loading stash box configuration...")
            config = self.stash.get_configuration()
            log.info("Retrieved configuration successfully in _load_stash_configuration")
            
            stash_boxes = config.get("general", {}).get("stashBoxes", [])
            log.info(f"Found {len(stash_boxes)} stash boxes in configuration")
            
            endpoints = {}
            endpoint_mapping = {
                'https://stashdb.org/graphql': 'stashdb',
                'https://theporndb.net/graphql': 'tpdb', 
                'https://fansdb.cc/graphql': 'fansdb'
            }
            
            for i, box in enumerate(stash_boxes):
                endpoint_url = box.get('endpoint', '')
                api_key = box.get('api_key', '')
                name = box.get('name', '')
                
                log.info(f"Stash box {i}: name='{name}', endpoint='{endpoint_url}', has_api_key={bool(api_key)}")
                
                # Map endpoint to our source names
                source_name = None
                for url_pattern, mapped_name in endpoint_mapping.items():
                    if url_pattern in endpoint_url:
                        source_name = mapped_name
                        break
                        
                if source_name and api_key:
                    endpoints[source_name] = {
                        'url': endpoint_url,
                        'api_key': api_key,
                        'name': name
                    }
                    log.info(f"Loaded configuration for {source_name}: {name} (API key: {api_key[:10]}...)")
                elif source_name:
                    log.warning(f"Found {source_name} endpoint but no API key")
                else:
                    log.debug(f"Skipping unrecognized endpoint: {endpoint_url}")
            
            log.info(f"Final endpoints configuration: {list(endpoints.keys())}")
            return endpoints
            
        except Exception as e:
            log.error(f"Failed to load Stash configuration: {e}")
            log.error(f"Exception type: {type(e)}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return {}

    def _build_sources_config(self) -> Dict[str, Dict[str, Any]]:
        """Build sources configuration with precedence based on plugin settings"""
        sources = {}
        precedence_order = [s.strip().lower() for s in self.plugin_config["sourcePrecedence"].split(",")]
        log.info(f"Endpoints available: {self.endpoints}")
        log.info(f"Source precedence order: {precedence_order}")
        
        for i, source in enumerate(precedence_order, 1):
            if source in self.endpoints:
                # Check if source is enabled in plugin config
                enable_key = f"enable{source.capitalize()}" if source != 'tpdb' else 'enableTPDB'
                if self.plugin_config.get(enable_key, True):
                    sources[source] = {
                        'precedence': i,
                        **self.endpoints[source]
                    }
        
        if not sources:
            log.error("No valid stash box endpoints found in configuration!")
            return {}
        
        log.info(f"Configured sources: {list(sources.keys())}")
        return sources

    def get_enabled_sources(self) -> List[str]:
        """Get list of enabled source names"""
        return list(self.sources.keys())
    
    def is_source_enabled(self, source: str) -> bool:
        """Check if a specific source is enabled"""
        return source in self.sources
    
    def get_source_config(self, source: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific source"""
        return self.sources.get(source)
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate configuration and return validation results"""
        validation_result = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "sources_configured": len(self.endpoints),
            "sources_enabled": len(self.sources),
            "plugin_config": self.plugin_config
        }
        
        # Check if any sources are configured
        if not self.sources:
            validation_result["valid"] = False
            validation_result["issues"].append("No external sources configured in Stash settings")
            
        # Check API keys
        for source, config in self.sources.items():
            if not config.get('api_key'):
                validation_result["valid"] = False
                validation_result["issues"].append(f"No API key configured for {source}")
                
        # Check plugin configuration
        if self.plugin_config["cacheExpirationHours"] < 1 or self.plugin_config["cacheExpirationHours"] > 168:
            validation_result["warnings"].append("Cache expiration should be between 1-168 hours")
            
        if self.plugin_config["rateLimit"] < 0 or self.plugin_config["rateLimit"] > 10:
            validation_result["warnings"].append("Rate limit should be between 0-10 seconds")
            
        return validation_result
    
    def reload_configuration(self):
        """Force reload of all configuration"""
        self._plugin_config = None
        self._endpoints = None
        self._sources = None
        log.info("Configuration reloaded")

    def get_setting(self, setting_name: str, default_value: Any = None) -> Any:
        """Get a plugin setting value with optional default"""
        return self.plugin_config.get(setting_name, default_value)
    
    def get_stashbox_endpoints(self) -> Dict[str, Dict[str, str]]:
        """Get all configured stashbox endpoints"""
        return self.endpoints
    
    def get_current_timestamp(self) -> str:
        """Get current timestamp as string"""
        from datetime import datetime
        return datetime.now().isoformat()
