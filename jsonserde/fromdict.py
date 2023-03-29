import typing
from typing import Type, List, Dict, NamedTuple, Set, Any
import dataclasses
from dataclasses import is_dataclass, dataclass
from functools import cached_property


# **********************************************************************************************************************
# Registry
# **********************************************************************************************************************

_dict_decoder_registry = dict()


def dict_decoder(cls):
    def wrapped(func):
        _dict_decoder_registry[cls] = func

        def call(*args, **kwargs):
            return func(*args, **kwargs)
        return call
    return wrapped


# **********************************************************************************************************************
# Error
# **********************************************************************************************************************

@dataclass
class DecodeError(Exception):
    value: Any
    target: Any
    path: str


@dataclass
class TypeCompileError(Exception):
    target: Any
    path: Any


@dataclass
class MissingRequiredAttributeError(DecodeError):
    attrs: List[str]

    def __str__(self):
        return f'path: {self.path}, target: {self.target}, value: {self.value}, attrs: {self.attrs}'


class NotAllowedTypeError(TypeCompileError):
    def __str__(self):
        return f'target: {self.target}, path: {self.path}'


class NotSupportedTypeError(DecodeError):
    def __str__(self):
        return f'path: {self.path}, target: {self.target}, value: {self.value}'


class WrongTypeError(DecodeError):
    def __str__(self):
        return f'path: {self.path}, target: {self.target}, value: {self.value}'


class WrongCollectionItemError(DecodeError):
    def __str__(self):
        return f'path: {self.path}, target: {self.target}, value: {self.value}'


@dataclass
class WrongCollectionError(DecodeError):
    details: list

    def __str__(self):
        formatted_details = '\n'.join([f'- {repr(d)}' for d in self.details])
        return f'path: {self.path}, target: {self.target}, value: {self.value}, details:\n{formatted_details}'


def _is_type_not_allowed(target) -> bool:
    _not_allowed = {
        dataclasses.InitVar,
        typing.Sequence,
    }

    return target in _not_allowed


# **********************************************************************************************************************
# Decode Dataclass (Nested Object)
# **********************************************************************************************************************

class FieldParam(NamedTuple):
    type: Type
    required: bool


class DataclsUtils:
    @staticmethod
    def is_field_required(field: dataclasses.Field) -> bool:
        return isinstance(field.default, dataclasses._MISSING_TYPE) \
               and isinstance(field.default_factory, dataclasses._MISSING_TYPE)

    @staticmethod
    def make_field_param_lookup(datacls) -> Dict[str, FieldParam]:
        result = {}
        for f in dataclasses.fields(datacls):
            if _is_type_not_allowed(f.type):
                raise NotAllowedTypeError(target=f.type, path=datacls)

            result[f.name] = FieldParam(type=f.type, required=_is_dataclass_field_required(f))

        return result


class DataclsProfile:
    def __init__(self, datacls):
        self._datacls = datacls

    def __repr__(self):
        return f'{type(self).__name__}(datacls={self._datacls})'

    @cached_property
    def field_param_lookup(self) -> Dict[str, FieldParam]:
        return DataclsUtils.make_field_param_lookup(self._datacls)

    @cached_property
    def required_field_names(self) -> Set[str]:
        return {
            field
            for field, (_, required) in self.field_param_lookup.items()
            if required
        }

    def compute_missing_fields(self, payload: dict) -> Set[str]:
        return self.required_field_names - payload.keys()


def _is_dataclass_field_required(field: dataclasses.Field) -> bool:
    return isinstance(field.default, dataclasses._MISSING_TYPE) \
           and isinstance(field.default_factory, dataclasses._MISSING_TYPE)


def _dataclass_field_type_lookup(datacls) -> Dict[str, FieldParam]:
    result = {}
    for f in dataclasses.fields(datacls):
        if _is_type_not_allowed(f.type):
            raise NotAllowedTypeError(f.type, msg=f'{f.type} is not supported yet.')

        result[f.name] = FieldParam(type=f.type, required=_is_dataclass_field_required(f))

    return result


def _decode_dataclass(value: dict, target, path):
    if not isinstance(value, dict):
        raise RuntimeError(f'{value} is not a dictionary!!!')

    dp = DataclsProfile(target)

    if missing_fields := dp.compute_missing_fields(value):
        raise MissingRequiredAttributeError(target=target, attrs=missing_fields, path=path, value=value)

    payload = {}
    for k, v in value.items():
        payload[k] = decode_input_internal(v, dp.field_param_lookup[k].type, f'{path}.{k}')

    return target(**payload)

# **********************************************************************************************************************
# Decode Typing Annotation
# **********************************************************************************************************************


def _decode_homogeneous_typing_collection(value, origin, inner, path):
    res = []
    errs = []
    for idx, item in enumerate(value):
        inner_path = f'{path}[{idx}]'

        try:
            decoded = decode_input_internal(item, inner, inner_path)
            res.append(decoded)
        except DecodeError:
            err = WrongCollectionItemError(
                value=item,
                target=inner,
                path=inner_path
            )
            errs.append(err)

    if errs:
        raise WrongCollectionError(
            value=value,
            target=origin,
            path=path,
            details=errs
        )

    return origin(res)


def _decode_typing_annotation(value, target, path):
    if (origin := target.__origin__) in {list, }:
        inner = target.__args__[0]
        return _decode_homogeneous_typing_collection(value, origin, inner, path)


# **********************************************************************************************************************
# Decode Input
# **********************************************************************************************************************

def decode_input_internal(value, target, path):
    if hasattr(target, '__origin__'):  # typing
        return _decode_typing_annotation(value, target, path)

    if is_dataclass(target):
        return _decode_dataclass(value, target, path)

    if isinstance(value, target):
        return value
    else:
        raise WrongTypeError(
            value=value,
            target=target,
            path=path
        )

    raise NotSupportedTypeError(value=value, target=target, path=path)


def decode_input(value, target: Type):
    return decode_input_internal(value, target, '$')
