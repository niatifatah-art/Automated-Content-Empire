# Production resources and rendering

ACE separates factual references from publishable media.

- **Reference-only:** articles, ordinary YouTube videos, unknown-rights images, vendor pages.
- **Publishable:** account-owned assets, public-domain/CC0, compatible CC BY, and approved stock licenses.
- **Blocked:** unknown, noncommercial, no-derivatives, incompatible ShareAlike, or all-rights-reserved media under the strict default.

```bash
ace assets add FILE --tags topic
ace resources find last --limit 8
ace resources list last
ace resources license last
```

The editing package contains a timeline, subtitles, resource mapping, and license metadata. FFmpeg can render the package locally. If no reusable asset is available, ACE creates a visible branded motion background and burned subtitles rather than a black frame.

```bash
ace edit package last
ace edit render last
ace status last
```
