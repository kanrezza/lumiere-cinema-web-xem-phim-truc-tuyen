<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ $name }} - Diễn viên</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root{--bg:#050505;--line:rgba(255,255,255,0.12);--text:#f5f5f5;--muted:#a3a3a3;--green:#00d760;}
        *{box-sizing:border-box;}
        body{margin:0;min-height:100vh;overflow-x:hidden;background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;}
        a{color:inherit;text-decoration:none;}

        .app{min-height:100vh;padding-left:88px;}

        .sidebar{position:fixed;inset:0 auto 0 0;z-index:20;width:88px;border-right:1px solid var(--line);background:rgba(3,5,8,0.92);backdrop-filter:blur(18px);display:flex;flex-direction:column;align-items:center;padding:24px 8px;gap:22px;}
        .side-item{width:70px;min-height:62px;display:grid;place-items:center;gap:6px;color:#8a8f98;font-size:12px;text-align:center;}
        .side-icon{width:30px;height:30px;display:grid;place-items:center;border:1px solid rgba(255,255,255,0.12);border-radius:12px;color:#cbd5e1;font-size:17px;}
        .side-item.active{color:var(--green);font-weight:900;}
        .side-item.active .side-icon{border-color:rgba(0,215,96,0.65);box-shadow:0 0 24px rgba(0,215,96,0.28);color:var(--green);}

        .topbar{position:fixed;inset:0 0 auto 88px;z-index:15;height:76px;display:flex;align-items:center;justify-content:space-between;gap:22px;padding:0 clamp(20px,4vw,52px);background:linear-gradient(180deg,rgba(3,5,8,0.92),rgba(3,5,8,0.35));backdrop-filter:blur(18px);}
        .brand{color:white;font-size:30px;font-weight:900;letter-spacing:0.08em;}
        .brand span{color:var(--green);}
        .menu{display:flex;gap:4px;color:#d0d3da;font-size:14px;font-weight:800;white-space:nowrap;}
        .menu-item{position:relative;}
        .menu-item>a{display:flex;align-items:center;gap:5px;padding:8px 12px;border-radius:10px;color:#d0d3da;transition:background 0.15s,color 0.15s;}
        .menu-item>a:hover,.menu-item:hover>a{background:rgba(255,255,255,0.1);color:white;}
        .menu-arrow{font-size:10px;opacity:0.6;}
        .dropdown{display:none;position:absolute;top:100%;left:0;min-width:210px;padding-top:10px;z-index:100;}
        .menu-item:hover .dropdown{display:block;}
        .dropdown-body{background:rgba(10,12,18,0.98);border:1px solid var(--line);border-radius:16px;padding:8px;backdrop-filter:blur(20px);box-shadow:0 20px 60px rgba(0,0,0,0.65);}
        .dropdown a{display:block;padding:9px 12px;border-radius:10px;color:#c8ccd6;font-size:13px;font-weight:800;}
        .dropdown a:hover{background:rgba(255,255,255,0.1);color:white;}
        .top-actions{display:flex;align-items:center;gap:12px;}
        .search-form{flex:1;}
        .search-input{width:100%;border:1px solid var(--line);border-radius:16px;padding:12px 14px;background:rgba(255,255,255,0.08);color:white;font:inherit;}
        .search-input::placeholder{color:#7b8190;}
        .profile-link{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;border:1px solid rgba(255,255,255,0.14);border-radius:999px;padding:0 14px;height:40px;background:rgba(255,255,255,0.07);color:#d1d5db;font:inherit;font-size:13px;font-weight:600;white-space:nowrap;}
        .profile-link:hover{border-color:rgba(0,215,96,0.5);color:#00d760;}
        .avatar-dot{width:24px;height:24px;border-radius:999px;background:rgba(0,215,96,0.2);border:1px solid rgba(0,215,96,0.4);display:grid;place-items:center;font-size:11px;font-weight:800;color:#00d760;flex-shrink:0;}
        .logout{border:0;border-radius:999px;padding:0 16px;height:40px;background:rgba(0,215,96,0.16);color:#bbf7d0;font:inherit;font-size:13px;font-weight:700;cursor:pointer;}
        .logout:hover{background:rgba(0,215,96,0.26);color:#fff;}

        .content{padding:96px clamp(20px,4vw,52px) 64px;}

        .actor-hero{display:flex;align-items:center;gap:20px;margin-bottom:40px;}
        .actor-avatar{width:72px;height:72px;border-radius:999px;background:rgba(0,215,96,0.12);border:2px solid rgba(0,215,96,0.35);display:grid;place-items:center;font-size:28px;font-weight:900;color:#00d760;flex-shrink:0;}
        .actor-avatar-img{width:72px;height:72px;border-radius:999px;object-fit:cover;border:2px solid rgba(0,215,96,0.35);flex-shrink:0;}
        .actor-bio{margin-top:10px;color:#9ca3af;font-size:14px;line-height:1.75;max-width:560px;}
        .actor-info h1{margin:0 0 4px;font-size:clamp(28px,4vw,48px);font-weight:900;letter-spacing:-0.04em;}
        .actor-info p{margin:0;color:#6b7280;font-size:14px;font-weight:500;}
        .back-link{display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(255,255,255,0.12);border-radius:999px;padding:7px 14px;font-size:13px;font-weight:700;color:#9ca3af;margin-bottom:28px;}
        .back-link:hover{color:#00d760;border-color:rgba(0,215,96,0.4);}

        .movie-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px;}
        .movie-card{border-radius:14px;overflow:hidden;background:#0d1117;border:1px solid rgba(255,255,255,0.07);transition:border-color 0.15s;}
        .movie-card:hover{border-color:rgba(0,215,96,0.35);}
        .movie-poster{aspect-ratio:2/3;background:#111820 center/cover no-repeat;}
        .movie-poster-empty{aspect-ratio:2/3;background:linear-gradient(135deg,#0d1117,#1a2535);display:grid;place-items:center;color:#374151;font-size:32px;}
        .movie-info{padding:10px 12px;}
        .movie-title{font-size:13px;font-weight:700;color:#e5e7eb;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .movie-meta{font-size:12px;color:#6b7280;margin-top:3px;}
        .star{color:#fbbf24;}
        .empty{text-align:center;color:#4b5563;padding:80px 20px;font-size:15px;}
    </style>
</head>
<body>
    <aside class="sidebar">
        <a class="side-item" href="{{ route('movies.index') }}">
            <span class="side-icon">⌂</span><span>Trang chủ</span>
        </a>
        <a class="side-item" href="{{ route('movies.index', ['cat' => 'phim-bo']) }}">
            <span class="side-icon">▣</span><span>Phim bộ</span>
        </a>
        <a class="side-item" href="{{ route('movies.index', ['cat' => 'phim-le']) }}">
            <span class="side-icon">▭</span><span>Phim lẻ</span>
        </a>
        <a class="side-item" href="{{ route('top-rated.index') }}">
            <span class="side-icon">★</span><span>Rating</span>
        </a>
        <a class="side-item" href="{{ route('history.index') }}">
            <span class="side-icon">↺</span><span>Lịch sử</span>
        </a>
        <a class="side-item" href="{{ route('watchlist.index') }}">
            <span class="side-icon">♥</span><span>Yêu thích</span>
        </a>
    </aside>

    <main class="app">
        <header class="topbar">
            <a class="brand" href="{{ route('movies.index') }}">LUMIERE<span>.</span></a>
            <nav class="menu">
                <div class="menu-item">
                    <a href="{{ route('movies.index') }}">Thể loại <span class="menu-arrow">▾</span></a>
                    <div class="dropdown"><div class="dropdown-body">
                        @foreach($categories as $cat)
                            <a href="{{ route('movies.index', ['cat' => $cat->slug]) }}">{{ $cat->name }}</a>
                        @endforeach
                    </div></div>
                </div>
                <div class="menu-item">
                    <a href="{{ route('movies.index', ['cat' => 'phim-bo']) }}">Phim Bộ <span class="menu-arrow">▾</span></a>
                    <div class="dropdown"><div class="dropdown-body">
                        <a href="{{ route('movies.index', ['cat' => 'phim-bo']) }}">Tất cả phim bộ</a>
                    </div></div>
                </div>
                <div class="menu-item">
                    <a href="{{ route('movies.index', ['cat' => 'phim-le']) }}">Phim Lẻ <span class="menu-arrow">▾</span></a>
                    <div class="dropdown"><div class="dropdown-body">
                        <a href="{{ route('movies.index', ['cat' => 'phim-le']) }}">Tất cả phim lẻ</a>
                    </div></div>
                </div>
                <div class="menu-item">
                    <a href="{{ route('movies.index', ['cat' => 'chieu-rap']) }}">Chiếu rạp <span class="menu-arrow">▾</span></a>
                    <div class="dropdown"><div class="dropdown-body">
                        <a href="{{ route('movies.index', ['cat' => 'chieu-rap']) }}">Tất cả phim chiếu rạp</a>
                    </div></div>
                </div>
                <a class="menu-item" href="{{ route('actors.index') }}" style="padding:8px 12px;border-radius:10px;color:#00d760;">Diễn viên</a>
            </nav>
            <div class="top-actions">
                <form class="search-form" method="GET" action="{{ route('movies.index') }}">
                    <input class="search-input" type="search" name="q" placeholder="Tìm kiếm phim, thể loại...">
                </form>
                <a class="profile-link" href="{{ route('profile.edit') }}">
                    <span class="avatar-dot">{{ mb_strtoupper(mb_substr(auth()->user()->name, 0, 1)) }}</span>
                    Chào, {{ explode(' ', auth()->user()->name)[0] }}
                </a>
                <form method="POST" action="{{ route('logout') }}">
                    @csrf
                    <button class="logout" type="submit">Đăng xuất</button>
                </form>
            </div>
        </header>

        <div class="content">
            <a class="back-link" href="{{ route('actors.index') }}">← Tất cả diễn viên</a>

            <div class="actor-hero">
                @if($profile && $profile->avatar)
                    <img class="actor-avatar-img" src="{{ $profile->avatarUrl() }}" alt="{{ $name }}" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'">
                    <div class="actor-avatar" style="display:none" aria-hidden="true">{{ mb_strtoupper(mb_substr($name, 0, 1)) }}</div>
                @else
                    <div class="actor-avatar">{{ mb_strtoupper(mb_substr($name, 0, 1)) }}</div>
                @endif
                <div class="actor-info">
                    <h1>{{ $name }}</h1>
                    <p>{{ $movies->count() }} phim tham gia</p>
                    @if($profile && $profile->bio)
                        <p class="actor-bio">{{ $profile->bio }}</p>
                    @endif
                </div>
            </div>

            @if($movies->isNotEmpty())
                <div class="movie-grid">
                    @foreach($movies as $movie)
                        <a class="movie-card" href="{{ route('movies.show', $movie) }}">
                            @if($movie->poster)
                                <div class="movie-poster" style="background-image:url('{{ $movie->posterUrl() }}')"></div>
                            @else
                                <div class="movie-poster-empty"></div>
                            @endif
                            <div class="movie-info">
                                <div class="movie-title">{{ $movie->title }}</div>
                                <div class="movie-meta">
                                    {{ $movie->year }}
                                    @if($movie->rating > 0)· <span class="star">★</span> {{ $movie->rating }}@endif
                                </div>
                            </div>
                        </a>
                    @endforeach
                </div>
            @else
                <div class="empty">Không tìm thấy phim nào.</div>
            @endif
        </div>
    </main>

    @if(auth()->check() && auth()->user()->role === 'admin')
    <div style="position:fixed;bottom:24px;right:24px;z-index:999;display:flex;border-radius:999px;border:1px solid rgba(255,255,255,0.1);background:rgba(5,5,5,0.9);backdrop-filter:blur(16px);padding:4px;gap:2px;box-shadow:0 4px 28px rgba(0,0,0,0.5);">
        <a href="{{ route('movies.index') }}" style="border-radius:999px;padding:8px 16px;font-size:13px;font-weight:700;background:#00d760;color:#03130a;text-decoration:none;">Website</a>
        <a href="{{ route('admin.dashboard') }}" style="border-radius:999px;padding:8px 16px;font-size:13px;font-weight:700;color:#4b5563;text-decoration:none;">Admin</a>
    </div>
    @endif
</body>
</html>
