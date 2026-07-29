# Platforms and Content Types

ACE ships with 6 platforms and 41 editable deliverable types.

## YouTube

`long_video`, `short`, `title`, `description`, `tags`, `thumbnail`, `community_post`

## TikTok

`short`, `caption`, `hook`, `series`, `live_outline`, `thumbnail`

## Instagram

`reel`, `carousel`, `post`, `story`, `caption`, `bio`, `thumbnail`

## Facebook

`post`, `long_post`, `reel`, `story`, `group_post`, `ad`, `thumbnail`

## X

`post`, `thread`, `reply`, `poll`, `space_outline`, `video_script`, `thumbnail`

## LinkedIn

`post`, `article`, `carousel`, `newsletter`, `video_script`, `poll`, `thumbnail`

## Examples

```bash
ace youtube long_video "Topic"
ace tt short "Topic"
ace insta carousel "Topic"
ace fb long_post "Topic"
ace x poll "Topic"
ace li newsletter "Topic"
```

## Candidate modes

```bash
--variants 1|3|5|10
--select manual|auto|hybrid
```

Hybrid recommends the AI-selected candidate but allows an interactive user to replace it. In non-interactive mode, hybrid accepts the recommendation.

## Extras

```bash
--extras caption,thumbnail
--all-extras
```

Without explicit flags, an interactive terminal can show a numbered menu after the primary content is generated.

## Catalog editing

The installed catalog is:

```bash
ace config path
```

Beside `config.json`, edit `content_catalog.json`. A type defines its aliases, task route, output format, constraints, and whether it belongs to a default pack.
