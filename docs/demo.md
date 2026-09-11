# Demo recording guide

This is a small, repeatable script for recording the public project demo.
Record with a clean browser profile and a local/mock provider so no API key,
private URL, or personal research history appears in the video.

## Storyboard

1. Start the backend and Vite frontend.
2. Enter a concrete question such as “How is generative AI changing higher
   education?”
3. Show the generated **Kế hoạch nghiên cứu** card and expand a long step list.
4. Click **Bắt đầu nghiên cứu** and show the live progress canvas and source
   chips.
5. Scroll through the final report and open one citation preview.
6. End on the repository README and configuration example.

## Export

- 1440×900 or 1920×1080;
- 30 fps;
- 60–120 seconds for the README embed;
- H.264 MP4 for video and a short 6–10 fps GIF only if the hosting platform
  needs a preview.

Do not commit local recordings under `docs/assets/local/`. Publish the MP4/GIF
on a release, GitHub asset, or a video host, then add the stable URL to the
Demo section in `README.md`.
