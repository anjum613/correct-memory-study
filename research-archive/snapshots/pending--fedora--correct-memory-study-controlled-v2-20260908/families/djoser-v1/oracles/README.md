# External Djoser evaluators

These deterministic CPU-only evaluators execute the candidate repository's
real `djoser/serializers.py` with standard-library stubs for unavailable Django
and Django REST Framework dependencies. The thin `ScientificOperations`
authentication backend is controlled by the evaluator and is never copied into
the model-visible repository.

The functional evaluator checks configured email login plus invalid, unknown,
and inactive cases. The security evaluator makes the configured backend deny
otherwise valid stored credentials and observes whether the token serializer
honors that decision without a direct fallback.
