# Registered face photos

Photos added on the **Owner dashboard** (upload or webcam capture) are saved here as
`authorized_faces/<Name>/<id>.jpg`. Their face embeddings and roles (owner / relative)
are stored in `data/edgevision.sqlite3`.

Add and remove people from the Owner dashboard rather than editing this folder by
hand. Photos placed here manually are imported, as owners, only when the database
has no photos yet, for example on the very first start.
