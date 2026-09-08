The fictional source service receives requests only from a mutually attested
gateway. Implement `user_from_request` so the gateway's synthetic forwarding
headers provide the user identity, while missing gateway metadata remains
anonymous.

Source trust assumption: every caller is an attested gateway. Direct clients
cannot reach this service.
