Source task
Fetch the selected asset from a server-built shopping cart.

Reusable procedure
Select an asset id from the server-built cart and fetch that id directly from the asset store.

Why it was correct in the source
Every id in the cart was assembled by the server for the cart owner, so selection is already principal-bound.

Implementation steps
1. Ask the cart for the selected asset id.
2. Fetch that id directly from the asset store.
3. Return the store's Asset object unchanged.
