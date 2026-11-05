# Lumière streaming interface

The current interface is implemented with Django templates, a single core stylesheet (`static/streaming.css`), scoped account styles (`static/account.css`) and native JavaScript. It does not load the previous app/design/motion stylesheets. The identity uses charcoal, warm white and coral, system typography and a distinct Lumière mark.

## Experience references

- [Netflix's TV experience](https://www.netflix.com/tudum/articles/netflix-new-homepage-layout-user-guide): reference for making choosing a film easier, visible navigation and relevant content rows. This local web interface is independently implemented; no Netflix code, logo, screen or brand assets are copied.
- [Plex Discover](https://www.plex.tv/discover/): reference for watchlist-oriented discovery and title detail navigation.
- Earlier exploration used [Nuxt Movies](https://github.com/nuxt/movies), [MUBI](https://mubi.com/en/memberships) and [Criterion Channel](https://www.criterionchannel.com/subscribe). No third-party template source was incorporated.

## Welcome and discovery use one interface

The public Welcome page is `/`; the movie browser is `/browse/`. Welcome remains visible for signed-in sessions and offers public sign-in/sign-up actions. Those entry actions send an existing signed-in session into the browser. Login keeps safe `next` targets and registration cannot replace an already signed-in account.

Both pages consume the same tokens and components: charcoal panels, warm white text, coral accent, sans typography, a 1440px container, the same logo and responsive header, and 44–48px buttons with an 8px radius. `static/landing.css` now owns Welcome layout only; it does not define another header, logo, font or palette. Account, VIP and quick-view styles use the same tokens.

Welcome introduces the actual published catalog through a poster wall. It uses the same movie data, `cinema_poster` artwork filter and `cinema/card.html` component as the browser. Its featured film links to that title's real detail page. Movie cards on both pages open the same native-dialog quick view with a permission-aware play/VIP action. The active Welcome does not use unrelated generated scenery.

The two pages have different roles: Welcome explains the service and invites registration/discovery; the browser adds search, filters and personal watch progress. Their navigation content follows those roles while visual dimensions and controls remain shared.

Pointer parallax, short entrance reveals, tab transitions and the watch-together illustration honor the shared reduced-motion preference. Authentication, published-only queries, signed HLS playback and membership checks are preserved.

## Discovery navigation

The library and Welcome headers expose Genre and Country as matching dropdowns, alongside the actor directory link. Country choices use normalized, published-only country counts, preserve the active genre and other catalog filters, and retain a link to `/countries/`. Both dropdowns share one disclosure controller so opening one closes the other. The dropdown uses published-only genre counts, preserves active catalog filters when changing genre, resets pagination and retains a link to `/genres/`. Its panel sits outside the scrollable navigation rail so it remains visible on mobile; keyboard opening, Escape, outside-click dismissal and a no-JavaScript link fallback are supported. Country and genre directories show counts from published films and link to filtered discovery results. The actor directory supports search, pagination and a filmography detail page; unpublished-only credits are not exposed.

Catalog filters for `country`, `category`, `actor`, title query, film format, access and sort combine and remain in pagination links. Country labels group existing case/whitespace variants without requiring a new database model. Invalid actor filters return an empty result safely. The mobile navigation scrolls horizontally and reveals the active destination without shifting vertical page position.

The current local catalog has country and genre records, but no actor records; the public actor page therefore uses the designed empty state. Staff can add actor records and associate them with films through the existing administration interface.

## Current behavior

- The feature stage prioritizes a real ready episode, with direct playback and up to three titles that have ready video. Tabs support mouse, arrow keys, Home and End. The Big Buck Bunny feature has a muted 16-second public preview, separately trimmed from the complete private film. Preview playback stops offscreen, on hidden tabs, when selecting a different film or when motion is disabled. A pause/play control is always available for that preview.
- Portrait browsing rows, genre shortcuts, search, filters and pagination use published database records. Seven local SVG posters combine the original demo photographs with individual film typography; no invented ratings or view counts. The first catalog row appears immediately below the feature stage, followed by personal watch progress.
- Continue-watching cards use the signed-in user's stored position; saved titles remain personal.
- The profile separates membership, personal information, security and billing, with compact fields and mobile navigation.
- The player keeps native controls as a fallback; enhanced controls add play/pause, ten-second seeking, timeline, volume and fullscreen. Existing authenticated HLS tickets and progress APIs remain in use.
- Motion follows device reduced-motion settings by default; the footer control allows explicit session opt-in. Loops stop offscreen or while the tab is hidden.
- Active VIP members see their rights and expiry by default; renewal options open explicitly. Purchase forms submit a plan ID and the server determines the price. VNPay remains unavailable until merchant configuration is present.

## Real test film and artwork

Big Buck Bunny (Blender Foundation, 2008) is imported as a complete 596.462-second 720p film with original credits. The private source was remuxed to MP4 and processed through the application's HLS worker into 100 segments. Film/source attribution appears on the detail and watch pages. See `static/imagery/SOURCES.md` for the CC BY 3.0 license and original sources.

The other existing photographic artwork illustrates the fictional demonstration catalog. Uploaded `Movie.backdrop` images drive wide feature and detail artwork. The demo catalog uses the authored portrait SVGs in `static/imagery/posters/`; other titles use their uploaded poster, backdrop or fallback artwork. Library and related-film cards keep their landscape layout.

## Appearance and profile images

The header theme control switches light/dark and persists the browser preference. Interface surfaces use shared theme tokens; cinematic artwork and the player retain readable dark overlays. Profile avatars are uploaded through a separate CSRF-protected form, validated and normalized to square WebP, then reused by the header and profile.
