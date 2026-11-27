# Photographic test fixtures

These images are used exclusively by the automated tests, never by the running
application's authorized-face database.

- `astronaut.png`: NASA portrait of astronaut Eileen Collins, public domain.
  Source: https://github.com/scikit-image/scikit-image/blob/v0.24.0/skimage/data/astronaut.png
- `grace_hopper.jpg`: U.S. Navy portrait of Rear Admiral Grace Hopper, public domain.
  Source: https://github.com/matplotlib/matplotlib/blob/v3.10.0/lib/matplotlib/mpl-data/sample_data/grace_hopper.jpg

Upstream repositories redistribute these public-domain government images as
scientific image-processing samples. Recognition tests compare distinct people
and an exact reference match; these are pipeline regression checks, not a
statistical evaluation of recognition accuracy in real deployments.
