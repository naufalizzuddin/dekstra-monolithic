from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        return response

    return Response({
        "error_type": type(exc).__name__,
        "error_message": str(exc)
    }, status=500)