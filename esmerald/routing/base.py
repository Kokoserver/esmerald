import re
from enum import Enum
from functools import partial
from inspect import Signature, isawaitable
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
    cast,
)

from esmerald.backgound import BackgroundTask, BackgroundTasks
from esmerald.datastructures import ResponseContainer
from esmerald.enums import MediaType
from esmerald.exceptions import ImproperlyConfigured
from esmerald.injector import Inject
from esmerald.kwargs import KwargsModel
from esmerald.permissions.utils import continue_or_raise_permission_exception
from esmerald.requests import Request
from esmerald.responses import ORJSONResponse, Response
from esmerald.routing.views import APIView
from esmerald.signature import SignatureModelFactory, get_signature_model
from esmerald.typing import Void
from esmerald.utils.helpers import is_async_callable, is_class_and_subclass
from esmerald.utils.sync import AsyncCallable
from pydantic import BaseConfig, Extra
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.responses import Response as StarletteResponse
from starlette.routing import Mount as Mount  # noqa
from starlette.types import Scope

if TYPE_CHECKING:
    from esmerald.applications import Esmerald
    from esmerald.permissions.types import Permission
    from esmerald.routing.router import HTTPHandler, WebSocketHandler
    from esmerald.types import (
        AsyncAnyCallable,
        ExceptionHandlers,
        OwnerType,
        ResponseCookies,
        ResponseHeaders,
        ResponseType,
    )
    from pydantic.typing import AnyCallable


PARAM_REGEX = re.compile("{([a-zA-Z_][a-zA-Z0-9_]*)(:[a-zA-Z_][a-zA-Z0-9_]*)?}")


T = TypeVar("T", bound="BaseHandlerMixin")


class ParamConf(BaseConfig):
    extra = Extra.allow


class BaseSignature:
    """
    In charge of handling the signartures of the handlers.
    """

    def create_signature_model(self, is_websocket: bool = False) -> None:
        """
        Creates a signature model for the given route.
        Websockets do not support methods.

        Args:
            is_websocket (bool, optional): If the signature should be created for a websocker or handler.
            override (bool, optional): Override dependency signature model.
        """
        if not self.signature_model:
            self.signature_model = SignatureModelFactory(
                fn=cast("AnyCallable", self.fn),
                dependency_names=self.dependency_names,
            ).create_signature_model()

        for dependency in list(self.get_dependencies().values()):
            if not dependency.signature_model:
                dependency.signature_model = SignatureModelFactory(
                    fn=dependency.dependency, dependency_names=self.dependency_names
                ).create_signature_model()

        kwargs_model = self.create_handler_kwargs_model()
        if not is_websocket:
            self.kwargs = kwargs_model
            for method in self.methods:
                self.route_map[method] = (self, kwargs_model)
        else:
            self.websocket_parameter_model = kwargs_model

    def create_handler_kwargs_model(self) -> "KwargsModel":
        """Method to create a KwargsModel for a given handler."""
        dependencies = self.get_dependencies()
        signature_model = get_signature_model(self)

        return KwargsModel.create_for_signature_model(
            signature_model=signature_model,
            dependencies=dependencies,
            path_parameters=self.path_parameters,
        )


class BaseResponseHandler:
    """
    In charge of handling the responses of the handlers.
    """

    def create_response_container_handler(
        self,
        cookies: "ResponseCookies",
        headers: Dict[str, Any],
        media_type: str,
        status_code: int,
    ) -> "AsyncAnyCallable":
        """Creates a handler fpr ResponseContainer Types"""

        async def response_content(
            data: ResponseContainer, app: "Esmerald", **kwargs: Dict[str, Any]
        ) -> StarletteResponse:
            _headers = {**self.get_headers(headers), **data.headers}
            _cookies = self.get_cookies(data.cookies, cookies)
            response = data.to_response(
                app=app,
                headers=_headers,
                status_code=status_code,
                media_type=media_type,
            )
            for cookie in _cookies:
                response.set_cookie(**cookie)
            return response

        return response_content

    def create_response_handler(
        self,
        cookies: "ResponseCookies",
        headers: Optional["ResponseHeaders"] = None,
        status_code: Optional[int] = None,
        media_type: Optional[str] = MediaType.TEXT,
    ) -> "AsyncAnyCallable":
        """Creates a handler function for Esmerald responses

        Args:
            cookies (ResponseCookies): The cookies to be passed to the response.
            status_code (Optional[int], optional): The status code to be returned. Defaults to 200.
            media_type (Optional[str], optional): The type of payload format. Defaults to "text/plain".

        Returns:
            AsyncAnyCallable: The application handler.
        """

        async def response_content(data: Response, **kwargs: Dict[str, Any]) -> StarletteResponse:
            _cookies = self.get_cookies(data.cookies, cookies)
            _headers = {
                **self.get_headers(headers),
                **data.headers,
                **self.allow_header,
            }

            for cookie in _cookies:
                data.set_cookie(**cookie)

            if status_code:
                data.status_code = status_code

            if media_type:
                data.media_type = media_type

            for header, value in _headers.items():
                data.headers[header] = value
            return data

        return response_content

    def create_json_response_handler(
        self, status_code: Optional[int] = None
    ) -> "AsyncAnyCallable":
        """Creates a handler function for Esmerald JSON responses"""

        async def response_content(data: Response, **kwargs: Dict[str, Any]) -> StarletteResponse:
            if status_code:
                data.status_code = status_code
            return data

        return response_content

    def create_starlette_response_handler(
        self,
        cookies: "ResponseCookies",
        headers: Optional["ResponseHeaders"] = None,
        media_type: Optional["MediaType"] = MediaType.TEXT,
    ) -> "AsyncAnyCallable":
        """Creates an handler for Starlette Responses."""

        async def response_content(
            data: StarletteResponse, **kwargs: Dict[str, Any]
        ) -> StarletteResponse:

            _cookies = self.get_cookies(cookies, [])
            _headers = {
                **self.get_headers(headers),
                **data.headers,
                **self.allow_header,
            }
            for cookie in _cookies:
                data.set_cookie(**cookie)

            data.media_type = media_type

            for header, value in _headers.items():
                data.headers[header] = value
            return data  # type: ignore

        return response_content

    def create_handler(
        self,
        background: Optional[Union["BackgroundTask", "BackgroundTasks"]],
        cookies: "ResponseCookies",
        headers: Dict[str, Any],
        media_type: str,
        response_class: "ResponseType",
        status_code: int,
    ) -> "AsyncAnyCallable":
        async def response_content(data: Any, **kwargs: Dict[str, Any]) -> StarletteResponse:

            data = await self.get_response_data(data=data)
            _cookies = self.get_cookies(cookies, [])
            # Making sure ORJSONResponse and JSONResponse are properly handled
            if isinstance(data, (JSONResponse, ORJSONResponse)):
                response = data
                response.status_code = status_code
                response.background = background
            else:
                response = response_class(
                    background=background,
                    content=data,
                    headers=headers,
                    media_type=media_type,
                    status_code=status_code,
                )

            for cookie in _cookies:
                response.set_cookie(**cookie)
            return response  # type: ignore

        return response_content

    async def get_response_for_request(
        self,
        scope: "Scope",
        request: Request,
        route: Union["HTTPHandler", "WebSocketHandler"],
        parameter_model: "KwargsModel",
    ) -> "StarletteResponse":
        """Handles creating a response instance and/or using cache.

        Args:
            scope: The Request's scope
            request: The Request instance
            route_handler: The HTTPRouteHandler instance
            parameter_model: The HTTPHandler's KwargsModel

        Returns:
            An instance of StarletteResponse or a subclass of it
        """
        response: Optional["StarletteResponse"] = None
        if not response:
            response = await self.call_handler_function(
                scope=scope,
                request=request,
                route=route,
                parameter_model=parameter_model,
            )

        return response

    async def call_handler_function(
        self,
        scope: "Scope",
        request: Request,
        route: Union["HTTPHandler", "WebSocketHandler"],
        parameter_model: "KwargsModel",
    ) -> "StarletteResponse":
        """Calls the before request handlers, retrieves any data required for
        the route handler, and calls the route handler's to_response method.

        This is wrapped in a try except block - and if an exception is raised,
        it tries to pass it to an appropriate exception handler - if defined.
        """
        response_data = None

        if not response_data:
            response_data = await self._get_response_data(
                route=route,
                parameter_model=parameter_model,
                request=request,
            )

        return await self.to_response(
            app=scope["app"],
            data=response_data,
        )

    @staticmethod
    async def _get_response_data(
        route: "HTTPHandler", parameter_model: "KwargsModel", request: Request
    ) -> Any:
        """
        Determines what kwargs are required for the given handler and assignes to the specific
        object dictionary.

        It supports more one object payload to be sent.
        """
        signature_model = get_signature_model(route)
        if parameter_model.has_kwargs:
            kwargs = parameter_model.to_kwargs(connection=request)
            request_data = kwargs.get("data")
            if request_data:
                kwargs["data"] = await request_data
            for dependency in parameter_model.expected_dependencies:
                kwargs[dependency.key] = await parameter_model.resolve_dependency(
                    dependency=dependency, connection=request, **kwargs
                )
            parsed_kwargs = signature_model.parse_values_from_connection_kwargs(
                connection=request, **kwargs
            )
        else:
            parsed_kwargs = {}
        if isinstance(route.owner, APIView):
            fn = partial(
                cast("AnyCallable", route.fn),
                route.owner,
                **parsed_kwargs,
            )
        else:
            fn = partial(cast("AnyCallable", route.fn), **parsed_kwargs)

        if is_async_callable(fn):
            return await fn()

        return fn()

    def get_response_handler(self) -> Callable[[Any], Awaitable[StarletteResponse]]:
        """
        Checks and validates the type of return response and maps to the corresponding
        handler with the given parameters.
        """
        if self._response_handler is Void:
            media_type = (
                self.media_type.value if isinstance(self.media_type, Enum) else self.media_type
            )

            response_class = self.get_response_class()
            headers = self.get_response_headers()
            cookies = self.get_response_cookies()

            if is_class_and_subclass(self.signature.return_annotation, ResponseContainer):
                handler = self.create_response_container_handler(
                    cookies=cookies,
                    media_type=self.media_type,
                    status_code=self.status_code,
                    headers=headers,
                )
            elif is_class_and_subclass(
                self.signature.return_annotation, (JSONResponse, ORJSONResponse)
            ):
                handler = self.create_json_response_handler(status_code=self.status_code)
            elif is_class_and_subclass(self.signature.return_annotation, Response):
                handler = self.create_response_handler(
                    cookies=cookies,
                    status_code=self.status_code,
                    media_type=self.media_type,
                    headers=headers,
                )
            elif is_class_and_subclass(self.signature.return_annotation, StarletteResponse):
                handler = self.create_starlette_response_handler(
                    cookies=cookies,
                    media_type=self.media_type,
                    headers=headers,
                )
            else:
                handler = self.create_handler(
                    background=self.background,
                    cookies=cookies,
                    headers=headers,
                    media_type=media_type,
                    response_class=response_class,
                    status_code=self.status_code,
                )
            self._response_handler = handler
        return cast(
            "Callable[[Any], Awaitable[StarletteResponse]]",
            self._response_handler,
        )


class BaseHandlerMixin(BaseSignature, BaseResponseHandler):
    """
    Base of HTTPHandler and WebSocketHandler.
    """

    @property
    def signature(self) -> Signature:
        """The Signature of 'self.fn'."""
        return Signature.from_callable(cast("AnyCallable", self.fn))

    @property
    def path_parameters(self) -> List[str]:
        """
        Gets the path parameters
        """
        parameters = set()
        for param_name, _ in self.param_convertors.items():
            parameters.add(param_name)
        return parameters

    @property
    def ownership_layers(self) -> List[Union[T, "OwnerType"]]:
        """
        Returns the handler from the app down to the route handler.
        """
        layers = []
        current: Any = self
        while current:
            layers.append(current)
            current = current.owner
        return list(reversed(layers))

    @property
    def dependency_names(self) -> Set[str]:
        """A unique set of all dependency names provided in the handlers ownership
        layers."""
        layered_dependencies = (layer.dependencies or {} for layer in self.ownership_layers)
        return {name for layer in layered_dependencies for name in layer.keys()}

    def resolve_permissions(self) -> List["Permission"]:
        """
        Returns all the permissions in the handler scope from the ownsership layers.
        """
        if self._permissions is Void:
            self._permissions = []
            for layer in self.ownership_layers:
                self._permissions.extend(layer.permissions or [])
            self._permissions = cast(
                "List[Permission]",
                [AsyncCallable(permissions) for permissions in self._permissions],
            )
        return cast("List[Permission]", self._permissions)

    def get_dependencies(self) -> Dict[str, Inject]:
        """
        Returns all dependencies of the handler function's starting from the ownership layers.
        """
        if not self.signature_model:
            raise RuntimeError(
                "get_dependencies cannot be called before a signature model has been generated"
            )
        if self._dependencies is Void:
            self._dependencies = {}
            for layer in self.ownership_layers:
                for key, value in (layer.dependencies or {}).items():
                    self.has_dependency_unique(
                        dependencies=self._dependencies,
                        key=key,
                        injector=value,
                    )
                    self._dependencies[key] = value
        return cast("Dict[str, Inject]", self._dependencies)

    @staticmethod
    def has_dependency_unique(dependencies: Dict[str, Inject], key: str, injector: Inject) -> None:
        """
        Validates that a given inject has not been already defined under a
        different key in any of the layers.
        """
        for dependency_key, value in dependencies.items():
            if injector == value:
                raise ImproperlyConfigured(
                    f"Injector for key {key} is already defined under the different key {dependency_key}. "
                    f"If you wish to override a inject, it must have the same key."
                )

    def get_exception_handlers(self) -> "ExceptionHandlers":
        """Resolves the exception_handlers by starting from the route handler
        and moving up.

        This method is memoized so the computation occurs only once.
        """
        resolved_exception_handlers = {}
        for layer in self.ownership_layers:
            resolved_exception_handlers.update(layer.exception_handlers or {})
        return resolved_exception_handlers

    def get_cookies(
        self, local_cookies: "ResponseCookies", other_cookies: "ResponseCookies"
    ) -> List[Dict[str, Any]]:
        """Given two lists of cookies, ensures the uniqueness of cookies by key and
        returns a normalized dict ready to be set on the response."""
        filtered_cookies = [*local_cookies]
        for cookie in other_cookies:
            if not any(cookie.key == c.key for c in filtered_cookies):
                filtered_cookies.append(cookie)
        normalized_cookies: List[Dict[str, Any]] = []
        for cookie in filtered_cookies:
            normalized_cookies.append(cookie.dict(exclude_none=True, exclude={"description"}))
        return normalized_cookies

    def get_headers(self, headers: "ResponseHeaders") -> Dict[str, Any]:
        """Given a dictionary of ResponseHeader, filters them and returns a
        dictionary of values.

        Args:
            headers: A dictionary of [ResponseHeader][esmerald.datastructures.ResponseHeader] values

        Returns:
            A string keyed dictionary of normalized values
        """
        return {k: v.value for k, v in headers.items()}

    async def get_response_data(self, data: Any) -> Any:
        """Gets the response's data by awaiting any async values.

        Args:
            data: An arbitrary value

        Returns:
            Value for the response body
        """
        if isawaitable(data):
            data = await data
        return data

    async def allow_connection(self, connection: "HTTPConnection") -> None:
        """Validates the connection.

        Handles with the permissions for each view (get, put, post, delete, patch...) after the request.
        Raises an appropriate exception if the request is not allowed.
        """
        for permission in self.resolve_permissions():
            permission = await permission()
            permission.has_permission(connection, self)
            continue_or_raise_permission_exception(connection, self, permission)
