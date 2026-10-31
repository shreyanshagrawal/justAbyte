# Malformed manifest fixture
# Line 2 is fine comment
# @trust-repo invalid-repo weight=0.5
# @trust-repo ghostty-org/ghostty weight=2.5
# @trust-repo my-org/my-repo weight=0.5
# @trust-repo
# @trust-repo peer/a weight=not_a_float
@invalid_handle
github:
:missing_platform
-
valid_user

