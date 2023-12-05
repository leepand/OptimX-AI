from optimx.testing.fixtures import (
    JSONTestResult,
    modellibrary_auto_test,
    modellibrary_fixture,
)
from optimx.testing.reference import ReferenceJson, ReferenceText

try:
    from optimx.testing.tf_serving import tf_serving_fixture
except NameError:
    # This occurs because type annotations in
    # optimx.core.models.tensorflow_model will raise
    # `NameError: name 'prediction_service_pb2_grpc' is not defined`
    # when tensorflow-serving-api is not installed
    pass

# flake8: noqa: F401
