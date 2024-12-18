from typing import Optional, Union

import pydantic
import pydantic_settings


class ModelkitSettings(pydantic_settings.BaseSettings):
    """
    Custom pydantic settings needed to allow setting both:
    - the validation alias
    - the field name
    And to prioritize the field name over the environment variable name.
    It aims at replacing the deprecated, pydantic 1.*, `env` argument to `Field`.
    It requires the use of the `validation_alias` and AliasChoices arguments in
    the child class.

    Example:
        class ServingSettings(ModelkitSettings):
            enable: bool = pydantic.Field(
                False,
                validation_alias=pydantic.AliasChoices(
                    "enable",
                    "MODELKIT_TF_SERVING_ENABLE",
                ),
            )
        assert ServingSettings().enable is False
        assert ServingSettings(enable=True).enable is True

        os.environ["MODELKIT_TF_SERVING_ENABLE"] = "True"
        assert ServingSettings().enable is True
        assert ServingSettings(enable=False).enable is False

    """

    model_config = pydantic.ConfigDict(extra="ignore")


class TFServingSettings(ModelkitSettings):
    enable: bool = pydantic.Field(False, env="OPTIMX_TF_SERVING_ENABLE")
    mode: str = pydantic.Field("rest", env="OPTIMX_TF_SERVING_MODE")
    host: str = pydantic.Field("localhost", env="OPTIMX_TF_SERVING_HOST")
    port: int = pydantic.Field(8501, env="OPTIMX_TF_SERVING_PORT")

    @pydantic.field_validator("port")
    @classmethod
    def default_serving_port(cls, v, values):
        if not v:
            v = 8500 if values.get("mode") == "grpc" else 8501
        return v


class CacheSettings(ModelkitSettings):
    cache_provider: Optional[str] = pydantic.Field(
        None,
        validation_alias=pydantic.AliasChoices(
            "cache_provider", "OPTIMX_CACHE_PROVIDER"
        ),
    )
    # cache_provider: Optional[str] = pydantic.Field(None, env="OPTIMX_CACHE_PROVIDER")


class RedisSettings(CacheSettings):
    host: str = pydantic.Field("localhost", env="OPTIMX_CACHE_HOST")
    port: int = pydantic.Field(6379, env="OPTIMX_CACHE_PORT")

    @pydantic.field_validator("cache_provider")
    def _validate_type(cls, v):
        if v != "redis":
            raise ValueError
        return v


class NativeCacheSettings(CacheSettings):
    implementation: str = pydantic.Field("LRU", env="OPTIMX_CACHE_IMPLEMENTATION")
    maxsize: int = pydantic.Field(128, env="OPTIMX_CACHE_MAX_SIZE")

    @pydantic.field_validator("cache_provider")
    def _validate_type(cls, v):
        if v != "native":
            raise ValueError
        return v


def cache_settings():
    s = CacheSettings()
    if s.cache_provider is None:
        return None
    try:
        return RedisSettings()
    except pydantic.ValidationError:
        pass
    try:
        return NativeCacheSettings()
    except pydantic.ValidationError:
        pass


class LibrarySettings(ModelkitSettings):
    lazy_loading: bool = pydantic.Field(False, env="OPTIMX_LAZY_LOADING")
    override_assets_dir: Optional[str] = pydantic.Field(
        None, env="OPTIMX_ASSETS_DIR_OVERRIDE"
    )
    enable_validation: bool = pydantic.Field(True, env="OPTIMX_ENABLE_VALIDATION")
    tf_serving: TFServingSettings = pydantic.Field(
        default_factory=lambda: TFServingSettings()
    )
    cache: Optional[Union[RedisSettings, NativeCacheSettings]] = pydantic.Field(
        default_factory=lambda: cache_settings()
    )

    class Config:
        env_prefix = ""
        extra = "allow"
