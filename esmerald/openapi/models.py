from typing import Any, Dict, List, Optional, Union

from openapi_schemas_pydantic.v3_1_0.contact import Contact as Contact
from openapi_schemas_pydantic.v3_1_0.discriminator import Discriminator as Discriminator
from openapi_schemas_pydantic.v3_1_0.encoding import Encoding as Encoding
from openapi_schemas_pydantic.v3_1_0.example import Example as Example
from openapi_schemas_pydantic.v3_1_0.external_documentation import (
    ExternalDocumentation as ExternalDocumentation,
)
from openapi_schemas_pydantic.v3_1_0.header import Header as Header
from openapi_schemas_pydantic.v3_1_0.info import Info as Info
from openapi_schemas_pydantic.v3_1_0.license import License as License
from openapi_schemas_pydantic.v3_1_0.link import Link as Link
from openapi_schemas_pydantic.v3_1_0.media_type import MediaType as MediaType
from openapi_schemas_pydantic.v3_1_0.oauth_flow import OAuthFlow as OpenOAuthFlow
from openapi_schemas_pydantic.v3_1_0.oauth_flows import OAuthFlows as OAuthFlows
from openapi_schemas_pydantic.v3_1_0.operation import Operation as Operation
from openapi_schemas_pydantic.v3_1_0.parameter import Parameter as Parameter
from openapi_schemas_pydantic.v3_1_0.path_item import PathItem as PathItem
from openapi_schemas_pydantic.v3_1_0.paths import Paths as Paths
from openapi_schemas_pydantic.v3_1_0.reference import Reference as Reference
from openapi_schemas_pydantic.v3_1_0.request_body import RequestBody as RequestBody
from openapi_schemas_pydantic.v3_1_0.response import Response as Response
from openapi_schemas_pydantic.v3_1_0.schema import Schema as Schema
from openapi_schemas_pydantic.v3_1_0.security_scheme import SecurityScheme as SecurityScheme
from openapi_schemas_pydantic.v3_1_0.server import Server as Server
from openapi_schemas_pydantic.v3_1_0.server_variable import ServerVariable as ServerVariable
from openapi_schemas_pydantic.v3_1_0.tag import Tag as Tag
from openapi_schemas_pydantic.v3_1_0.xml import XML as XML
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal

from esmerald.openapi.enums import APIKeyIn, SecuritySchemeType


class APIKey(SecurityScheme):
    type: Literal["apiKey", "http", "mutualTLS", "oauth2", "openIdConnect"] = Field(
        default=SecuritySchemeType.apiKey,
        alias="type",
    )
    param_in: APIKeyIn = Field(alias="in")
    name: str


class HTTPBase(SecurityScheme):
    type: Literal["apiKey", "http", "mutualTLS", "oauth2", "openIdConnect"] = Field(
        default=SecuritySchemeType.http,
        alias="type",
    )
    scheme: str


class HTTPBearer(HTTPBase):
    scheme: Literal["bearer"] = "bearer"
    bearerFormat: Optional[str] = None


class OAuthFlow(OpenOAuthFlow):
    scopes: Dict[str, str] = {}


class OAuth2(SecurityScheme):
    type: Literal["apiKey", "http", "mutualTLS", "oauth2", "openIdConnect"] = Field(
        default=SecuritySchemeType.oauth2, alias="type"
    )
    flows: OAuthFlows


class OpenIdConnect(SecurityScheme):
    type: Literal["apiKey", "http", "mutualTLS", "oauth2", "openIdConnect"] = Field(
        default=SecuritySchemeType.openIdConnect, alias="type"
    )
    openIdConnectUrl: str


SecuritySchemeUnion = Union[APIKey, HTTPBase, OAuth2, OpenIdConnect, HTTPBearer]


class Components(BaseModel):
    schemas: Optional[Dict[str, Union[Schema, Reference]]] = None
    responses: Optional[Dict[str, Union[Response, Reference]]] = None
    parameters: Optional[Dict[str, Union[Parameter, Reference]]] = None
    examples: Optional[Dict[str, Union[Example, Reference]]] = None
    requestBodies: Optional[Dict[str, Union[RequestBody, Reference]]] = None
    headers: Optional[Dict[str, Union[Header, Reference]]] = None
    securitySchemes: Optional[Dict[str, Union[SecurityScheme, Reference]]] = None
    links: Optional[Dict[str, Union[Link, Reference]]] = None
    callbacks: Optional[Dict[str, Union[Dict[str, PathItem], Reference, Any]]] = None
    pathItems: Optional[Dict[str, Union[PathItem, Reference]]] = None

    model_config = ConfigDict(extra="allow")


class OpenAPI(BaseModel):
    openapi: str
    info: Info
    jsonSchemaDialect: Optional[str] = None
    servers: Optional[List[Dict[str, Union[str, Any]]]] = None
    paths: Optional[Dict[str, Union[PathItem, Any]]] = None
    webhooks: Optional[Dict[str, Union[PathItem, Reference]]] = None
    components: Optional[Components] = None
    security: Optional[List[Dict[str, List[str]]]] = None
    tags: Optional[List[Tag]] = None
    externalDocs: Optional[ExternalDocumentation] = None
    model_config = ConfigDict(extra="allow")
