from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


class ClosedSignupAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False
