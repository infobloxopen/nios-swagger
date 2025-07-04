#!/usr/bin/env python3
"""
Generate OpenAPI spec for Infoblox WAPI
--------------------------------------

This script generates self-contained OpenAPI specifications for Infoblox NIOS WAPI objects.
It organizes objects by groups (dns, dhcp, ipam, grid, etc.) defined in config.json.

Author: Jeenitkumar Khatri
"""
import requests
import json
import yaml
import argparse
import urllib3
import os
import re
import sys
import logging
from datetime import datetime
from collections import defaultdict

# Disable SSL warnings for convenience in dev environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
import logging.handlers

# Create logs directory if it doesn't exist
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(logs_dir, exist_ok=True)

# Set up logging to file and console
log_file = os.path.join(logs_dir, 'openapi_generator.log')

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console handler
        logging.FileHandler(log_file)  # File handler
    ]
)
# Create a logger for this module
logger = logging.getLogger('openapi_generator')


# Set up a specific logger for this module
class OpenAPIGenerator:
    def __init__(self, config_file=None):
        """Initialize the OpenAPI generator
        
        Args:
            config_file: Path to configuration file
        """
        # Load configuration
        if not config_file:
            raise ValueError("Config file must be provided")
        
        self.config = self._load_config(config_file)
        
        # Set credentials and connection info
        self.hostname = self.config.get("connection", {}).get("hostname")
        self.username = self.config.get("connection", {}).get("username")
        self.password = self.config.get("connection", {}).get("password")
        self.wapi_version = self.config.get("connection", {}).get("wapi_version")
        self.verify_ssl = self.config.get("connection", {}).get("verify_ssl", False)
        
        # Validate required configuration
        if not all([self.hostname, self.username, self.password, self.wapi_version]):
            raise ValueError("Connection details (hostname, username, password, wapi_version) must be provided in config")
        
        # Set output format (json or yaml)
        self.output_format = self.config.get("output", {}).get("format", "json").lower()
        if self.output_format not in ["json", "yaml"]:
            logger.warning(f"Invalid output format '{self.output_format}' specified, defaulting to 'json'")
            self.output_format = "json"
        
        # Command line options that override config
        self.group = None
        self.objects = []
        
        # Set up object groups from config
        self.object_groups = self.config.get("object_groups", {})

        # Set up object types for Func Call
        self.func_call_fields = self.config.get("func_callbacks", {})
        
        # Create inverse mapping from object to group
        self.object_to_group = {}
        for group_name, objects_list in self.object_groups.items():
            for obj in objects_list:
                self.object_to_group[obj] = group_name
        
        # Set up output directory
        output_config = self.config.get("output", {})
        self.format = output_config.get("format", "json").lower()
        if self.format not in ["json", "yaml"]:
            logger.warning(f"Invalid output format '{self.format}', defaulting to 'json'")
            self.format = "json"
        
        self.output_dir = output_config.get("directory", "output")
        if not self.output_dir:
            raise ValueError("Output directory must be specified in config")
        
        # Create format-specific subdirectory
        #self.output_dir = os.path.join(self.output_dir, self.format)
        os.makedirs(self.output_dir, exist_ok=True)

        
        # Keep track of created schemas to avoid duplicates
        self.created_schemas = set()
    
    def _load_config(self, config_file):
        """Load configuration from file
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file {config_file} not found.")
        except json.JSONDecodeError:
            raise ValueError(f"Configuration file {config_file} is not valid JSON.")
    
    def set_options(self, group=None, objects=None, hostname=None, username=None, 
                   password=None, wapi_version=None, output_dir=None):
        """Set command line options that override config
        
        Args:
            group: Object group to process
            objects: Specific objects to process
            hostname: Infoblox hostname (overrides config)
            username: Infoblox username (overrides config)
            password: Infoblox password (overrides config)
            wapi_version: Infoblox WAPI version (overrides config)
            output_dir: Output directory (overrides config)
        """
        self.group = group
        self.objects = objects or []
        
        # Override connection details
        if hostname:
            self.hostname = hostname
        if username:
            self.username = username
        if password:
            self.password = password
        if wapi_version:
            self.wapi_version = wapi_version
        if output_dir:
            self.output_dir = output_dir
            os.makedirs(self.output_dir, exist_ok=True)
        
    def get_objects_to_process(self):
        """Get the list of objects to process based on group or specified objects
        
        Returns:
            List of object types to process
        """
        if self.objects:
            return self.objects
        
        if self.group and self.group in self.object_groups:
            return self.object_groups[self.group]
        
        # Default to all objects in all groups
        all_objects = []
        for objects in self.object_groups.values():
            all_objects.extend(objects)
        return all_objects
    
    def fetch_schema(self, object_type):
        """Fetch schema from NIOS WAPI
        
        Args:
            object_type: The NIOS object type to fetch
        
        Returns:
            Schema JSON
        """
        url = f"https://{self.hostname}/wapi/v{self.wapi_version}/{object_type}?_schema_version=2&_schema&_get_doc=1"
        logger.info(f"Fetching schema for {object_type} from {url}")
        
        try:
            response = requests.get(
                url, 
                auth=(self.username, self.password), 
                verify=self.verify_ssl, 
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"Failed to fetch schema for {object_type}: {response.status_code} - {response.text.strip()}"
                logger.error(error_msg)
                # Add to tracked failures
                if not hasattr(self, 'failed_objects'):
                    self.failed_objects = {}
                self.failed_objects[object_type] = {
                    "status_code": response.status_code,
                    "message": response.text.strip() if response.text else "No error message provided",
                    "url": url
                }
                return None
            
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error fetching schema for {object_type} (URL: {url}): {str(e)}"
            logger.error(error_msg)
            if not hasattr(self, 'failed_objects'):
                self.failed_objects = {}
            self.failed_objects[object_type] = {
                "status_code": "Network Error",
                "message": str(e),
                "url": url
            }
            return None
        except Exception as e:
            error_msg = f"Unexpected error fetching schema for {object_type} (URL: {url}): {str(e)}"
            logger.error(error_msg)
            if not hasattr(self, 'failed_objects'):
                self.failed_objects = {}
            self.failed_objects[object_type] = {
                "status_code": "Exception",
                "message": str(e),
                "url": url
            }
            return None
    
    def process_field(self, field):
        """Process a single field from the schema
        
        Args:
            field: Field data from schema
            
        Returns:
            Processed field data
        """
        field_name = field.get("name", "")
        if not field_name:
            return None
        # print(f"Processing field: {field_name}")
        # # Check if this is a function call field that should be ignored
        # if field_name == "nextavailableip":
        #     import pdb; pdb.set_trace()
        #     logger.debug(f"Skipping ipv4addrs field: {field_name}")
        #     return None
        # if field.get("wapi_primitive") == "funccall":
        #     logger.debug(f"Skipping function call field: {field_name}")
        #     return None
        
        # Get operation support
        supports = field.get("supports", "")
        
        # Determine read/write access
        readonly = 'r' in supports and 'w' not in supports
        writeonly = 'w' in supports and 'r' not in supports
        
        # Check if this is a delete-only field
        deleteonly = 'd' in supports and 'r' not in supports and 'w' not in supports
        
        # Determine field type
        field_types = field.get("type", [])
        if not field_types or not isinstance(field_types, list):
            field_types = ["string"]
        
        field_type = field_types[0] if field_types else "string"
        is_array = field.get("is_array", False)
        
        # Format field type for special cases
        original_type = field_type  # Keep original type for reference
        
        # Handle arrays
        if is_array:
            field_type = "array"
            
        # Clean description
        description = field.get("doc", "")
        if description:
            description = re.sub(r'[\n\r\t\f\v]', ' ', description)
            description = re.sub(r'\s+', ' ', description)
            description = description.strip()
        
        # Process searchable/filtering
        searchable_by = field.get("searchable_by", "")
        supports_filtering = bool(searchable_by)
        
        # Track required fields
        required = field.get("required", False)
        
        # Check for enum values
        enum_values = field.get("enum_values", None) if "enum_values" in field else None
        
        # Handle nested schema
        nested_schema = None
        if "schema" in field and field["schema"]:
            nested_schema = field["schema"]
        
        return {
            "name": field_name,
            "type": field_type,
            "original_type": original_type, 
            "description": description,
            "readonly": readonly,
            "writeonly": writeonly,
            "deleteonly": deleteonly,
            "supports_filtering": supports_filtering,
            "searchable_by": searchable_by,
            "required": required,
            "is_array": is_array,
            "enum": enum_values,
            "supports": supports,
            "nested_schema": nested_schema
        }
    
    def process_schema(self, schema, object_type):
        """Process the raw schema into a format suitable for our OpenAPI spec
        
        Args:
            schema: Raw schema from WAPI
            object_type: The object type
            
        Returns:
            Processed schema data
        """
        if not schema:
            return None
        
        type_name = schema.get("type", object_type)
        raw_fields = schema.get("fields", [])
        
        # Process restrictions
        restrictions = []
        if "restrictions" in schema and schema["restrictions"]:
            if isinstance(schema["restrictions"], list):
                restrictions = schema["restrictions"]
            elif isinstance(schema["restrictions"], dict) and "list" in schema["restrictions"]:
                restrictions = schema["restrictions"].get("list", [])
                
        # Process cloud restrictions
        cloud_restrictions = []
        if "cloud_additional_restrictions" in schema:
            if isinstance(schema["cloud_additional_restrictions"], list):
                cloud_restrictions = schema["cloud_additional_restrictions"]
            elif isinstance(schema["cloud_additional_restrictions"], dict) and "list" in schema["cloud_additional_restrictions"]:
                cloud_restrictions = schema["cloud_additional_restrictions"].get("list", [])
            
        # Process fields
        processed_fields = {}
        filtering_fields = []
        required_fields = []
        nested_schemas = []
        
        for field in raw_fields:
            # print(f"Processing field: {field.get('name', 'unknown')}")
            processed_field = self.process_field(field)

            # Skip if field is not processed or is a function call
            if not processed_field or field.get("wapi_primitive") == "funccall":
                continue
            
            field_name = processed_field["name"]
            
            # Track filtering fields
            if processed_field["supports_filtering"]:
                filtering_fields.append(field_name)
                
            # Track required fields
            if processed_field["required"]:
                required_fields.append(field_name)
            
            # Track nested schemas
            if processed_field["nested_schema"]:
                nested_schema_name = self.to_pascal_case(f"{type_name}_{field_name}")
                nested_schemas.append({
                    "name": nested_schema_name,
                    "schema": processed_field["nested_schema"],
                    "field_name": field_name
                })
                processed_field["nested_schema_name"] = nested_schema_name
            
            processed_fields[field_name] = processed_field
        
        # Determine object group
        # If a single object is requested via --objects, use "custom" group
        if self.objects and len(self.objects) == 1:
            group = "custom"
        else:
            group = self.object_to_group.get(object_type, "other")
        
        # Generate schema names in PascalCase if configured
        if self.config.get("schema_options", {}).get("pascal_case_schemas", True):
            schema_name = self.to_pascal_case(type_name)
        else:
            schema_name = type_name.replace(":", "_")
            
        response_schema_name = f"List{schema_name}Response"
        
        # Determine operations based on restrictions
        supports_create = "create" not in restrictions
        supports_delete = "delete" not in restrictions
        
        # Check for additional operation restrictions in cloud_additional_restrictions
        if cloud_restrictions:
            if "create" in cloud_restrictions:
                supports_create = False
            if "delete" in cloud_restrictions:
                supports_delete = False
        
        # Determine MODIFY support by checking if there are fields with 'w' in supports
        supports_modify = any('w' in field_details.get("supports", "") for field_details in processed_fields.values())
        
        return {
            "object_type": type_name,
            "object_name": type_name.replace(":", "_").lower(),
            "schema_name": schema_name,
            "response_schema_name": response_schema_name,
            "fields": processed_fields,
            "filtering_fields": filtering_fields,
            "required_fields": required_fields,
            "nested_schemas": nested_schemas,
            "supports_create": supports_create,
            "supports_delete": supports_delete,
            "supports_modify": supports_modify,
            "group": group,
            "schema_version": schema.get("schema_version", "2"),
            "restrictions": restrictions,
            "cloud_restrictions": cloud_restrictions
        }
    
    def to_snake_case(self, object_name):
        """Convert object_name to snake_case
        
        Args:
            object_name: PascalCase string to convert
            
        Returns:
            snake_case version of the string
        """
        if not object_name:
            return ""
            
        # Replace colon with underscore
        return object_name.replace(':', '_')
    
    def to_pascal_case(self, snake_str):
        """Convert snake_case or colon:separated to PascalCase

        Args:
            snake_str: String or list of strings to convert
            
        Returns:
            PascalCase string or list of PascalCase strings
        """
        # Handle list input
        if isinstance(snake_str, list):
            return [self.to_pascal_case(item) for item in snake_str]
            
        if not snake_str:
            return ""
            
        # Replace colon with underscore
        snake_str = snake_str.replace(':', '_')
        
        # Split by underscore
        words = snake_str.split('_')
        
        # Capitalize each word
        return ''.join(word.capitalize() for word in words)
    
    def generate_common_parameters(self):
        """Generate common parameters shared across all APIs
        
        Returns:
            Dictionary of common parameters
        """
        return {
            "ReturnFields": {
                "name": "_return_fields",
                "in": "query",
                "description": "Enter the field names followed by comma",
                "required": False,
                "schema": {
                    "type": "string"
                }
            },
            "ReturnFieldsPlus": {
                "name": "_return_fields+",
                "in": "query",
                "description": "Enter the field names followed by comma, this returns the required fields along with the default fields",
                "required": False,
                "schema": {
                    "type": "string"
                }
            },
            # "ExtensibleAttributesParam": {
            #     "name": "extattrs",
            #     "in": "query",
            #     "description": "Extensible attributes associated with the object.",
            #     "required": False,
            #     "schema": {
            #         "type": "object"
            #     }
            # },
            "MaxResults": {
                "name": "_max_results",
                "in": "query",
                "description": "Enter the number of results to be fetched",
                "required": False,
                "schema": {
                    "type": "integer",
                    "format": "int32",
                    "minimum": 1
                }
            },
            "ReturnAsObject": {
                "name": "_return_as_object",
                "in": "query",
                "description": "Select 1 if result is required as an object",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [0, 1]
                }
            },
            "Paging": {
                "name": "_paging",
                "in": "query",
                "description": "Control paging of results",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [0, 1]
                }
            },
            "PageId": {
                "name": "_page_id",
                "in": "query",
                "description": "Page id for retrieving next page of results",
                "required": False,
                "schema": {
                    "type": "string"
                }
            },
            "ProxySearch": {
                "name": "_proxy_search",
                "in": "query",
                "description": "Search Grid members for data",
                "required": False,
                "schema": {
                    "type": "string"
                }
            },
            "Schema": {
                "name": "_schema",
                "in": "query",
                "description": "Return schema for this object type",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [0, 1]
                }
            },
            "SchemaVersion": {
                "name": "_schema_version",
                "in": "query",
                "description": "Schema version to use",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [1, 2]
                }
            },
            "GetDoc": {
                "name": "_get_doc",
                "in": "query",
                "description": "Return documentation with schema",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [0, 1]
                }
            },
            "SchemaSearchable": {
                "name": "_schema_searchable",
                "in": "query",
                "description": "Return searchable fields with schema",
                "required": False,
                "schema": {
                    "type": "integer",
                    "enum": [0, 1]
                }
            },
            "Inheritance": {
                "name": "_inheritance",
                "in": "query",
                "description": "If this option is set to True, fields which support inheritance, will display data properly.",
                "required": False,
                "schema": {
                    "type": "boolean"
                }
            },
            "filters": {
                "name": "filters",
                "in": "query",
                "schema": {
                    "type": "object",
                    "additionalProperties": True
                },
                "style": "form",
                "explode": False
            },
            "ExtAttrFilters": {
                "name": "extattrfilter",
                "in": "query",
                "schema": {
                    "type": "object",
                    "additionalProperties": True
                },
                "style": "form",
                "explode": False
            },
            "Method": {
                "name": "_method",
                "in": "query",
                "description": "Enter the method type for the request",
                "required": False,
                "schema": {
                    "type": "string"
                }
            },
            "Body": {
                "name": "body",
                "in": "query",
                "schema": {
                    "type": "object"
                }
            }
        }
    
    def generate_extensible_attributes_schema(self):
        """Generate the ExtensibleAttributes schema
        
        Returns:
            ExtensibleAttributes schema definition
        """
        return {
                "type": "object",
                "properties": {
                    "value": {
                        # "type": "string",
                        "description": "The value of the extensible attribute."
                    }
                },
                "required": [
                    "value"
                ],
                "description": "Extensible attributes associated with the object."
            }
    
    def convert_field_type_to_openapi(self, field_details):
        """Convert Infoblox field type to OpenAPI type
        
        Args:
            field_details: Field details containing type information
            
        Returns:
            Dictionary with OpenAPI type properties
        """
        field_type = field_details["type"]
        original_type = field_details["original_type"]
        
        # Start with basic property definition
        property_def = {
            "type": "string",  # Default type
            "description": field_details["description"]
        }
        
        # Map common types
        type_mapping = {
            "string": "string",
            "uint": "integer",
            "int": "integer",
            "integer": "integer",
            "bool": "boolean",
            "timestamp": "integer",
            "enum": "string",
            "extattr": "object"
        }

        # If it's a standard type, set it
        if field_type in type_mapping:
            property_def["type"] = type_mapping[field_type]
        elif field_details.get("parent_property") == "is_array":
            # The struct that are array type but does not have struct and ref then not make it Object.
            pass
        else:
            print(f"field_type: {field_type} and name {field_details.get('name')}")
            # TODO: Handle special cases for Infoblox types.
            property_def["type"] = "object"
        
        # Add format for special types
        format_mapping = {
            "timestamp": "int64",
            "uint": "int64",
            "int": "int64",
        }
        
        if field_type in format_mapping:
            property_def["format"] = format_mapping[field_type]
        
        # For special types like "awsrte53recordinfo", add original type in enum
        if field_type not in type_mapping and original_type:
            property_def["enum"] = [original_type]
        
        # Add enum values if present
        if field_details.get("enum"):
            property_def["enum"] = field_details["enum"]
        
        # Add access modifiers
        if field_details["readonly"]:
            property_def["readOnly"] = True
        
        if field_details["writeonly"]:
            property_def["writeOnly"] = True
        
        return property_def
    
    def process_nested_schema_fields(self, nested_schema, schemas_data):
        """Process nested schema fields
        
        Args:
            nested_schema: Nested schema data
            schemas_data: Schemas data to add nested schemas to
            
        Returns:
            Updated schemas data
        """
        schema_name = nested_schema["name"]
        schema_data = nested_schema["schema"]
        
        # Skip if already processed
        if schema_name in self.created_schemas:
            return schemas_data
        
        self.created_schemas.add(schema_name)
        
        schemas_data[schema_name] = {
            "type": "object",
            "properties": {}
        }
        
        for field in schema_data.get("fields", []):
            processed_field = self.process_field(field)
            
            if not processed_field:
                continue
            
            field_name = processed_field["name"]
            # print(f"Processing field: {field_name} in nested schema: {schema_name}")
            # Create property definition using consistent method
            property_def = self.convert_field_type_to_openapi(processed_field)
            # Deleting the type to avoid duplication if $ref is used
            # print(f"Property definition: {property_def}")
            
            # Add examples if configured
            if self.config.get("schema_options", {}).get("include_examples", True):
                if property_def.get("type") == "string":
                    property_def["example"] = f"Example {field_name}"
                elif property_def.get("type") == "integer":
                    property_def["example"] = 1
                elif property_def.get("type") == "boolean":
                    property_def["example"] = False
            
            # Handle nested schema
            if processed_field.get("nested_schema"):
                nested_schema_name = self.to_pascal_case(f"{schema_name}_{field_name}")
                property_def["$ref"] = f"#/components/schemas/{nested_schema_name}"
                
                # Process this nested schema too
                schemas_data = self.process_nested_schema_fields({
                    "name": nested_schema_name,
                    "schema": processed_field["nested_schema"],
                    "field_name": field_name
                }, schemas_data)
            
            # Handle array of nested schema
            elif processed_field["is_array"] and processed_field.get("nested_schema_name"):
                property_def["type"] = "array"
                property_def["items"] = {
                    "$ref": f"#/components/schemas/{processed_field['nested_schema_name']}"
                }
            
            # Handle regular arrays
            elif processed_field["is_array"]:
                property_def["type"] = "array"
                item_type = self.convert_field_type_to_openapi({
                    "type": processed_field["original_type"],
                    "original_type": processed_field["original_type"],
                    "description": "",
                    "readonly": False,
                    "writeonly": False
                })
                
                property_def["items"] = {
                    "type": item_type["type"]
                }
                
                # Add enum to items if present
                if "enum" in item_type:
                    property_def["items"]["enum"] = item_type["enum"]
            if "$ref" in property_def:
                del property_def["type"]
            schemas_data[schema_name]["properties"][field_name] = property_def
        
        return schemas_data
    
    def generate_schemas_for_objects(self, schemas):
        """Generate schema definitions from processed schemas
        
        Args:
            schemas: List of processed schemas
            
        Returns:
            Dictionary of schema definitions
        """
        schemas_data = {}
        
        # Reset created schemas tracking
        self.created_schemas = set()
        
        # Add ExtensibleAttributes schema
        schemas_data["ExtAttrs"] = self.generate_extensible_attributes_schema()
        
        # Process each schema
        for schema in schemas:
            # Main schema
            schema_name = schema["schema_name"]
            schemas_data[schema_name] = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "_ref": {
                        "type": "string",
                        "description": "The reference to the object."
                    }
                }
            }
            
            # Add required fields if present
            if schema["required_fields"]:
                schemas_data[schema_name]["required"] = schema["required_fields"]
            
            # Add properties
            for field_name, field_details in schema["fields"].items():
                # Convert type to OpenAPI
                property_def = self.convert_field_type_to_openapi(field_details)
                special_fields = self.func_call_fields
                additional_property_def = {}
                if field_name == "_ref":
                    continue
                elif field_name == "extattrs":
                    property_def["additionalProperties"] = {
                        "$ref": "#/components/schemas/ExtAttrs"
                    }
                elif field_name in special_fields.get(schema["object_type"], []):
                    print(f"Hello - Found callback field '{field_name}' for object type '{schema['object_type']}'")
                    # TODO: Implementing Func CAll
                    del property_def["type"]
                    property_def["oneOf"] = [
                        {
                            "type": "string",
                            # "title": "network",
                            "description": f"{schema['object_type']}: {field_details.get('description')}",
                        },
                        {
                                "type": "object",
                                # "title": f"{field_name}FuncCall",
                                "description": f"{schema['object_type']}: {field_details.get('description')}",
                                "properties": {
                                    "_object_function": {
                                        "type": "string"
                                    },
                                    "_parameters": {
                                        "type": "object"
                                    },
                                    "_result_field": {
                                        "type": "string"
                                    },
                                    "_object": {
                                        "type": "string"
                                    },
                                    "_object_parameters": {
                                        "type": "object"
                                    }
                                }
                        }

                    ]
                    if field_name in ["network"]:
                        property_def["oneOf"][1]["properties"]["_object_ref"] = {
                            "type": "string",
                            "description": "A WAPI object reference on which the function calls. Either _object or _object_ref must be set."
                        }
                    # Add new property for function call
                    additional_property_def.update({"$ref": "#/components/schemas/FuncCall"})

                # Handle nested schema
                if field_details.get("nested_schema_name"):
                    if field_details["is_array"]:
                        property_def["type"] = "array"
                        property_def["items"] = {
                            "$ref": f"#/components/schemas/{field_details['nested_schema_name']}"
                        }
                    else:
                        property_def = {
                            "$ref": f"#/components/schemas/{field_details['nested_schema_name']}"
                        }
                
                # Handle regular arrays
                elif field_details["is_array"]:
                    property_def["type"] = "array"
                    item_type = self.convert_field_type_to_openapi({
                        "type": field_details["original_type"],
                        "original_type": field_details["original_type"],
                        "description": "",
                        "readonly": False,
                        "writeonly": False,
                        "parent_property": "is_array" 
                    })
                    
                    property_def["items"] = {
                        "type": item_type["type"]
                    }
                    
                    # Add enum to items if present
                    if "enum" in item_type:
                        property_def["items"]["enum"] = item_type["enum"]
                
                # Add examples where appropriate
                if self.config.get("schema_options", {}).get("include_examples", True):
                    if property_def.get("type") == "string":
                        property_def["example"] = f"Example {field_name}"
                    elif property_def.get("type") == "integer":
                        property_def["example"] = 1
                    elif property_def.get("type") == "boolean":
                        property_def["example"] = False
                
                schemas_data[schema_name]["properties"][field_name] = property_def
                if additional_property_def:
                    schemas_data[schema_name]["properties"]['func_call'] = additional_property_def
                    # Add FuncCall schema if not already present
                    if "FuncCall" not in schemas_data:
                        schemas_data["FuncCall"] = {
                            "type": "object",
                            "description": "Function Call attribute",
                            "required": [
                              "attribute_name"
                            ],
                            "properties": {
                              "attribute_name": {
                                "type": "string",
                                "description": "The attribute to be called."
                              },
                              "_object_function": {
                                "type": "string",
                                "description": "The function to be called."
                              },
                              "_parameters": {
                                "type": "object",
                                "description": "The parameters for the function."
                              },
                              "_result_field": {
                                "type": "string",
                                "description": "The result field of the function."
                              },
                              "_object": {
                                "type": "string",
                                "description": "The object to be called."
                              },
                              "_object_parameters": {
                                "type": "object",
                                "description": "The parameters for the object."
                              }
                            }
                        }
                        if field_name in ["network"]:
                            schemas_data["FuncCall"]["properties"]["_object_ref"] = {
                                "type": "string",
                                "description": "A WAPI object reference on which the function calls. Either _object or _object_ref must be set."
                            }
            
            # Process nested schemas
            for nested_schema in schema["nested_schemas"]:
                schemas_data = self.process_nested_schema_fields(nested_schema, schemas_data)
            
            # Response list schema - Using oneOf to support both array and object formats
            response_schema_name = schema["response_schema_name"]
            schemas_data[response_schema_name] = {
                "oneOf": [
                    {
                        "description": f"The response format to retrieve __{schema_name}__ objects.",
                        "type": "array",
                        "title": f"{response_schema_name}Array",
                        "items": {
                            "$ref": f"#/components/schemas/{schema_name}"
                        }
                    },
                    {
                        "description": f"The response format to retrieve __{schema_name}__ objects.",
                        "type": "object",
                        "title": f"{response_schema_name}Object",
                        "properties": {
                            "result": {
                                "type": "array",
                                "items": {
                                    "$ref": f"#/components/schemas/{schema_name}"
                                }
                            }
                        }
                    }
                ]
            }
            
            # Create response schema
            if schema["supports_create"]:
                create_schema_name = f"Create{schema_name}Response"
                schemas_data[create_schema_name] = {
                "oneOf": [
                    {
                        "description": f"The response format to create __{schema_name}__ in object format.",
                        "type": "object",
                        "title": f"Create{schema_name}ResponseAsObject",
                        "properties": {
                            "result": {
                                "$ref": f"#/components/schemas/{schema_name}"
                            }
                        }
                    },
                    {
                        "description": f"The response format to create __{schema_name}__.",
                        "type": "string",
                        "title": f"Create{schema_name}Response"
                    }
                ]
            }
            
            # Get single object response schema
            get_schema_name = f"Get{schema_name}Response"
            schemas_data[get_schema_name] = {
                "oneOf": [
                    {
                        "$ref": f"#/components/schemas/{schema_name}"
                    },
                    {
                        "description": f"The response format to retrieve __{schema_name}__ objects.",
                        "type": "object",
                        "additionalProperties": False,
                        "title": f"Get{schema_name}ResponseObjectAsResult",
                        "properties": {
                            "result": {
                                "$ref": f"#/components/schemas/{schema_name}"
                            }
                        }
                    }
                ]
            }
            
            # Update response schema
            update_schema_name = f"Update{schema_name}Response"
            schemas_data[update_schema_name] = {
                "oneOf": [
                    {
                        "description": f"The response format to update __{schema_name}__ in object format.",
                        "type": "object",
                        "title": f"Update{schema_name}ResponseAsObject",
                        "properties": {
                            "result": {
                                "$ref": f"#/components/schemas/{schema_name}"
                            }
                        }
                    },
                    {
                        "description": f"The response format to update __{schema_name}__ .",
                        "type": "string",
                        "title": f"Update{schema_name}Response"
                    }
                ]
            }
        
        return schemas_data
    
    def generate_group_api(self, group, schemas):
        """Generate an API file for a specific object group
        
        Args:
            group: Group name
            schemas: List of schemas in this group
            
        Returns:
            Path to the generated file
        """
        # Set up API info from config
        api_info = self.config.get("api_info", {})
        api = {
            "openapi": "3.0.0",
            "info": {
                "title": f"Infoblox {group.upper()} API",
                "description": f"OpenAPI specification for Infoblox NIOS WAPI {group.upper()} objects",
                "version": self.wapi_version,
                "contact": api_info.get("contact", {
                    "name": "Infoblox",
                    "url": "https://www.infoblox.com"
                })
            },
            "tags": [],
            "paths": {},
            "components": {
                "parameters": {},
                "schemas": {}
            }
        }
        
        # Add tags - create a set of existing tags first for O(1) lookups
        existing_tags = {tag["name"] for tag in api["tags"]}
        
        for schema in schemas:
            object_type = schema["object_type"]
            if object_type not in existing_tags:
                api["tags"].append({
                    "name": self.to_pascal_case(object_type),
                    # "name": object_type,
                    "description": f"Operations for {object_type} objects"
                })
                # Add to existing_tags to avoid duplicates in future iterations
                #existing_tags.add(self.to_snake_case(object_type))
                existing_tags.add(object_type)
        
        # Add common parameters
        common_params = self.generate_common_parameters()
        api["components"]["parameters"] = common_params
        
        # Add schemas
        api["components"]["schemas"] = self.generate_schemas_for_objects(schemas)
        
        # Add paths
        for schema in schemas:
            object_type = schema["object_type"]
            
            # GET collection
            api["paths"][f"/{object_type}"] = {
                "get": {
                    "tags": [self.to_pascal_case(object_type)],
                    # "tags": [object_type],
                    "operationId": f"{self.to_pascal_case(object_type)}List",
                    "summary": f"Retrieve {object_type} objects",
                    "description": f"Returns a list of {object_type} objects matching the search criteria",
                    "parameters": [
                        {"$ref": "#/components/parameters/ReturnFields"},
                        {"$ref": "#/components/parameters/ReturnFieldsPlus"},
                        # {"$ref": "#/components/parameters/ExtensibleAttributesParam"},
                        {"$ref": "#/components/parameters/MaxResults"},
                        {"$ref": "#/components/parameters/ReturnAsObject"},
                        {"$ref": "#/components/parameters/Paging"},
                        {"$ref": "#/components/parameters/PageId"},
                        {"$ref": "#/components/parameters/filters"},
                        {"$ref": "#/components/parameters/ExtAttrFilters"},
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful operation",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": f"#/components/schemas/{schema['response_schema_name']}"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request"
                        },
                        "401": {
                            "description": "Unauthorized"
                        },
                        "403": {
                            "description": "Forbidden"
                        },
                        "404": {
                            "description": "Not found"
                        }
                    },
                    "security": [{"basicAuth": []}]
                }
            }
            
            # # Add filtering parameters to Get Call
            # for field_name in schema["filtering_fields"]:
            #     field_detail = schema["fields"].get(field_name, {})
                
            #     # Use consistent type mapping
            #     property_def = self.convert_field_type_to_openapi(field_detail)
            #     param_type = property_def.get("type", "string")
                
            #     api["paths"][f"/{object_type}"]["get"]["parameters"].append({
            #         "name": field_name,
            #         "in": "query",
            #         "description": field_detail.get("description", f"Filter by {field_name}"),
            #         "required": False,
            #         "schema": {
            #             "type": param_type
            #         }
            #     })
            
            # POST (create) - check for create restriction
            if schema["supports_create"]:
                api["paths"][f"/{object_type}"]["post"] = {
                    "tags": [self.to_pascal_case(object_type)],
                    # "tags": [object_type],
                    "operationId": f"{self.to_pascal_case(object_type)}Create",
                    "summary": f"Create a {object_type} object",
                    "description": f"Creates a new {object_type} object",
                    "parameters": [
                        {"$ref": "#/components/parameters/ReturnFields"},
                        {"$ref": "#/components/parameters/ReturnFieldsPlus"},
                        {"$ref": "#/components/parameters/ReturnAsObject"}
                    ],
                    "requestBody": {
                        "description": "Object data to create",
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{schema['schema_name']}"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Object created successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": f"#/components/schemas/Create{schema['schema_name']}Response"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request"
                        },
                        "401": {
                            "description": "Unauthorized"
                        },
                        "403": {
                            "description": "Forbidden"
                        }
                    },
                    "security": [{"basicAuth": []}],
                    "x-tf-resource": f"nios_{group}_{self.to_snake_case(object_type)}",
                    "x-tf-datasource": f"nios_{group}_{self.to_snake_case(object_type)}",
                    # "x-sdk-default-ext-attrs": True
                    # TODO: Add the fields that supports function call
                    #"x-sdk-function-call": [self.to_pascal_case(object_type)]
                }
                # Add ExtAttrs extension if the schema has extensible attributes to POST call
                if "extattrs" in schema["fields"]:
                    api["paths"][f"/{object_type}"]["post"]["x-sdk-default-ext-attrs"] = True
                # Add extension for function call if applicable
                if object_type in self.func_call_fields:
                    func_field = self.func_call_fields.get(schema["object_type"], [])
                    # Add fields that support function call
                    api["paths"][f"/{object_type}"]["post"]["x-sdk-post-function-call"] = [self.to_pascal_case(field) for field in func_field]
                    api["paths"][f"/{object_type}"]["post"]["x-tf-function-call"] = True
            else:
                # If create is not supported, Create dummy POST operation
                if self.config.get("create_dummy_post"):
                    api["paths"][f"/{object_type}"]["post"] = {
                        "tags": [self.to_pascal_case(object_type)],
                        # "tags": [object_type],
                        "operationId": f"{self.to_pascal_case(object_type)}Create",
                        "summary": f"Create operation not supported for {object_type}",
                        "description": f"Create operation is not supported for {object_type} objects",
                        "responses": {
                            "405": {
                                "description": "Method Not Allowed"
                            }
                        },
                    }
            # TODO: Add PUT as GET operation with _method for Struct fields only for the object has struct filed to search.
            
            # api["paths"][f"/{object_type}"]["put"] = {
            #         "tags": [object_type],
            #         "summary": f"Use PUT call as GET operation with _method for a Struct field of a {object_type} object",
            #         "description": f"Use PUT call as GET operation with _method for a Struct field of a {object_type} object",
            #         "parameters": [
            #             {"$ref": "#/components/parameters/ReturnFields"},
            #             {"$ref": "#/components/parameters/ReturnFieldsPlus"},
            #             {"$ref": "#/components/parameters/ReturnAsObject"},
            #             {"$ref": "#/components/parameters/MaxResults"},
            #             {"$ref": "#/components/parameters/Method"},
            #             # {"$ref": "#/components/parameters/Body"}
            #         ],
            #         "requestBody": {
            #             "description": "Object data to create",
            #             "required": True,
            #             "content": {
            #                 "application/json": {
            #                     "schema": {
            #                         "$ref": f"#/components/schemas/{schema['schema_name']}"
            #                     }
            #                 }
            #             }
            #         },
            #         "responses": {
            #             "200": {
            #                 "description": "OK",
            #                 "content": {
            #                     "application/json": {
            #                         "schema": {
            #                             "$ref": f"#/components/schemas/{schema['response_schema_name']}"
            #                         }
            #                     }
            #                 }
            #             },
            #             "400": {
            #                 "description": "Bad request"
            #             },
            #             "401": {
            #                 "description": "Unauthorized"
            #             },
            #             "403": {
            #                 "description": "Forbidden"
            #             },
            #             "404": {
            #                 "description": "Not found"
            #             }
            #         },
            #         "security": [{"basicAuth": []}],
            #         "x-sdk-default-ext-attrs": True
            #         # TODO: Add the fields that supports function call
            #         #"x-sdk-function-call": [self.to_pascal_case(object_type)]
            #     }
            

            # Individual object operations
            api["paths"][f"/{object_type}/{{reference}}"] = {
                "get": {
                    "tags": [self.to_pascal_case(object_type)],
                    # "tags": [object_type],
                    "operationId": f"{self.to_pascal_case(object_type)}Read",
                    "summary": f"Get a specific {object_type} object",
                    "description": f"Returns a specific {object_type} object by reference",
                    "parameters": [
                        {
                            "name": "reference",
                            "in": "path",
                            "description": f"Reference of the {object_type} object",
                            "required": True,
                            "schema": {
                                "type": "string"
                            }
                        },
                        {"$ref": "#/components/parameters/ReturnFields"},
                        {"$ref": "#/components/parameters/ReturnFieldsPlus"},
                        {"$ref": "#/components/parameters/ReturnAsObject"}
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful operation",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        # "$ref": f"#/components/schemas/{schema['schema_name']}"
                                        "$ref": f"#/components/schemas/Get{schema['schema_name']}Response"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request"
                        },
                        "401": {
                            "description": "Unauthorized"
                        },
                        "403": {
                            "description": "Forbidden"
                        },
                        "404": {
                            "description": "Not found"
                        }
                    },
                    "security": [{"basicAuth": []}]
                }
            }
            
            # PUT (update)
            if schema["supports_modify"]:
                api["paths"][f"/{object_type}/{{reference}}"]["put"] = {
                    "tags": [self.to_pascal_case(object_type)],
                    # "tags": [object_type],
                    "operationId": f"{self.to_pascal_case(object_type)}Update",
                    "summary": f"Update a {object_type} object",
                    "description": f"Updates a specific {object_type} object by reference",
                    "parameters": [
                        {
                            "name": "reference",
                            "in": "path",
                            "description": f"Reference of the {object_type} object",
                            "required": True,
                            "schema": {
                                "type": "string"
                            }
                        },
                        {"$ref": "#/components/parameters/ReturnFields"},
                        {"$ref": "#/components/parameters/ReturnFieldsPlus"},
                        {"$ref": "#/components/parameters/ReturnAsObject"}
                    ],
                    "requestBody": {
                        "description": "Object data to update",
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{schema['schema_name']}"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Object updated successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": f"#/components/schemas/Update{schema['schema_name']}Response"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request"
                        },
                        "401": {
                            "description": "Unauthorized"
                        },
                        "403": {
                            "description": "Forbidden"
                        },
                        "404": {
                            "description": "Not found"
                        }
                    },
                    "security": [{"basicAuth": []}]
                }

                # Add ExtAttrs extension if the schema has extensible attributes to PUT call
                if "extattrs" in schema["fields"]:
                    api["paths"][f"/{object_type}/{{reference}}"]["put"]["x-sdk-default-ext-attrs"] = True
                # Add extension for function call if applicable
                if object_type in self.func_call_fields:
                    func_field = self.func_call_fields.get(schema["object_type"], [])
                    # Add fields that support function call
                    api["paths"][f"/{object_type}/{{reference}}"]["put"]["x-sdk-put-function-call"] = [self.to_pascal_case(field) for field in func_field]
                    api["paths"][f"/{object_type}/{{reference}}"]["put"]["x-tf-function-call"] = True

            # DELETE
            if schema["supports_delete"]:
                delete_params = [
                    {
                        "name": "reference",
                        "in": "path",
                        "description": f"Reference of the {object_type} object",
                        "required": True,
                        "schema": {
                            "type": "string"
                        }
                    }
                ]
                
                # Add delete-specific parameters
                for field_name, field_details in schema["fields"].items():
                    if field_details.get("deleteonly"):
                        property_def = self.convert_field_type_to_openapi(field_details)
                        delete_params.append({
                            "name": field_name,
                            "in": "query",
                            "description": field_details.get("description", f"Delete option: {field_name}"),
                            "required": False,
                            "schema": {
                                "type": property_def.get("type", "string")
                            }
                        })
                
                api["paths"][f"/{object_type}/{{reference}}"]["delete"] = {
                    "tags": [self.to_pascal_case(object_type)],
                    # "tags": [object_type],
                    "operationId": f"{self.to_pascal_case(object_type)}Delete",
                    "summary": f"Delete a {object_type} object",
                    "description": f"Deletes a specific {object_type} object by reference",
                    "parameters": delete_params,
                    "responses": {
                        "200": {
                            "description": "Object deleted successfully"
                        },
                        "400": {
                            "description": "Bad request"
                        },
                        "401": {
                            "description": "Unauthorized"
                        },
                        "403": {
                            "description": "Forbidden"
                        },
                        "404": {
                            "description": "Not found"
                        }
                    },
                    "security": [{"basicAuth": []}]
                }
        
        # Determine file extension and format based on output_format
        extension = "json" if self.output_format == "json" else "yaml"
        filename = f"{group}.{extension}"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            if self.output_format == "json":
                # Write as JSON
                indent = 4 if self.config.get("output", {}).get("format_json", True) else None
                json.dump(api, f, indent=indent)
            else:
                # Write as YAML
                yaml.dump(api, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Generated {group} API file: {filepath} in {self.output_format.upper()} format")
        return filepath
    
    def generate_all(self):
        """Generate all OpenAPI files
        
        Returns:
            Dictionary with paths to generated files
        """
        objects_to_process = self.get_objects_to_process()
        logger.info(f"Processing {len(objects_to_process)} objects")
        
        all_processed_schemas = []
        
        # Initialize tracking for failed objects
        if not hasattr(self, 'failed_objects'):
            self.failed_objects = {}
            
        for obj_type in objects_to_process:
            logger.info(f"\nProcessing {obj_type}...")
            
            # Fetch and process schema
            raw_schema = self.fetch_schema(obj_type)
            if not raw_schema:
                logger.warning(f"Skipping {obj_type} due to schema fetch error")
                continue
                
            processed_schema = self.process_schema(raw_schema, obj_type)
            if not processed_schema:
                logger.warning(f"Skipping {obj_type} due to schema processing error")
                if obj_type not in self.failed_objects:
                    self.failed_objects[obj_type] = {
                        "status_code": "Processing Error",
                        "message": "Failed to process schema data",
                        "url": f"https://{self.hostname}/wapi/v{self.wapi_version}/{obj_type}?_schema_version=2&_schema&_get_doc=1"
                    }
                continue
                
            all_processed_schemas.append(processed_schema)
        
        if not all_processed_schemas:
            logger.error("Error: No objects were successfully processed.")
            return {"groups": {}}
        
        # Group schemas by group
        grouped_schemas = defaultdict(list)
        for schema in all_processed_schemas:
            grouped_schemas[schema["group"]].append(schema)
        
        # Generate group-specific API files
        group_filepaths = {}
        for group, schemas in grouped_schemas.items():
            filepath = self.generate_group_api(group, schemas)
            group_filepaths[group] = filepath
        
        # Log summary of failed objects
        if hasattr(self, 'failed_objects') and self.failed_objects:
            failures_count = len(self.failed_objects)
            logger.warning("\nFailed to process %s objects:", failures_count)

            # print object list
            print("\n".join(f"  - {obj_type}" for obj_type in self.failed_objects.keys()))
            
            # Ensure logs directory exists within the script's directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            logs_dir = os.path.join(script_dir, 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            # Create a dedicated failures log file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            failures_log_file = os.path.join(logs_dir, f'failed_objects_{timestamp}.log')
            failures_json_file = os.path.join(logs_dir, f'failed_objects_{timestamp}.json')
            failures_logger = logging.getLogger('failures_logger')
            
            # Configure a dedicated file handler for failures
            if not failures_logger.handlers:
                failures_handler = logging.FileHandler(failures_log_file)
                failures_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
                failures_logger.setLevel(logging.INFO)
                failures_logger.addHandler(failures_handler)
            
            # Log header to failures log
            failures_logger.info(f"=== FAILED OBJECTS SUMMARY ({failures_count} objects) ===")
            # failures_logger.info(f"Date: {logging.Formatter().formatTime(None, '%Y-%m-%d %H:%M:%S')}")
            failures_logger.info(f"WAPI Version: {self.wapi_version}")
            failures_logger.info(f"Hostname: {self.hostname}")
            failures_logger.info(f"Username: {self.username}")
            failures_logger.info("="*50)
            
            # Group failures by status code for better analysis
            failures_by_status = defaultdict(list)
            for obj_type, error_info in self.failed_objects.items():
                status = error_info.get("status_code", "Unknown")
                failures_by_status[status].append(obj_type)
            
            # Log status summary
            failures_logger.info("\nFAILURES BY STATUS CODE:")
            for status, objects in failures_by_status.items():
                failures_logger.info(f"  {status}: {len(objects)} objects")
            failures_logger.info("="*50)
            
            # Log each failure to both the main logger and the failures logger
            for obj_type, error_info in self.failed_objects.items():
                status = error_info.get("status_code", "Unknown")
                message = error_info.get("message", "No error message")
                url = error_info.get("url", "No URL provided")
                group = self.object_to_group.get(obj_type, "unknown_group")
                
                # Truncated message for main log
                truncated_message = message
                if len(message) > 100:
                    truncated_message = message[:100] + "..."
                logger.warning(f"  - {obj_type}: {status} - {truncated_message}")
                
                # Detailed message for failures log
                failures_logger.info(f"\nObject Type: {obj_type}")
                failures_logger.info(f"Group: {group}")
                failures_logger.info(f"Status Code: {status}")
                failures_logger.info(f"URL: {url}")
                failures_logger.info(f"Error Message: {message}")
                failures_logger.info("-"*50)
            
            # Export failures to JSON for programmatic analysis
            try:
                with open(failures_json_file, 'w') as f:
                    # Create a structured report with more metadata
                    failure_report = {
                        "metadata": {
                            "timestamp": timestamp,
                            "wapi_version": self.wapi_version,
                            "hostname": self.hostname,
                            "total_objects_processed": len(objects_to_process),
                            "total_failures": failures_count,
                            "failure_rate": f"{(failures_count / len(objects_to_process)) * 100:.2f}%",
                            "summary_by_status": {status: len(objects) for status, objects in failures_by_status.items()}
                        },
                        "failures": self.failed_objects
                    }
                    json.dump(failure_report, f, indent=2)
                logger.warning(f"Detailed failure information written to:")
                logger.warning(f"  - Log file: {failures_log_file}")
                logger.warning(f"  - JSON report: {failures_json_file}")
            except Exception as e:
                logger.error(f"Failed to write JSON failure report: {str(e)}")
        
        return {"groups": group_filepaths}

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Generate OpenAPI specs for Infoblox WAPI')
    parser.add_argument('--config', type=str, required=True, help='Path to configuration file')
    parser.add_argument('--hostname', type=str, help='Infoblox hostname (overrides config)')
    parser.add_argument('--username', type=str, help='Infoblox username (overrides config)')
    parser.add_argument('--password', type=str, help='Infoblox password (overrides config)')
    parser.add_argument('--wapi_version', type=str, help='Infoblox WAPI version (overrides config)')
    parser.add_argument('--group', type=str, help='Object group to process (dns, dhcp, grid, ipam, dtc)')
    parser.add_argument('--objects', nargs='+', help='Specific objects to process')
    parser.add_argument('--output_dir', type=str, help='Output directory (overrides config)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set debug level if requested
    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        # Create generator with config
        generator = OpenAPIGenerator(config_file=args.config)
        
        # Set options from command line arguments
        generator.set_options(
            group=args.group,
            objects=args.objects,
            hostname=args.hostname,
            username=args.username,
            password=args.password,
            wapi_version=args.wapi_version,
            output_dir=args.output_dir
        )
        
        # Generate API files
        generated_files = generator.generate_all()
        
        if not generated_files["groups"]:
            logger.error("\nNo API files were generated. Check your input parameters and try again.")
            return 1
            
        logger.info("\nGeneration completed successfully!")
        logger.info("Group API files:")
        for group, filepath in generated_files["groups"].items():
            logger.info(f"  - {group}: {filepath}")
        
        return 0
    except Exception as e:
        logger.error(f"Error during generation: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())