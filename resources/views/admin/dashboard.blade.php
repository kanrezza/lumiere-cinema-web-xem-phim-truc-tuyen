<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Admin Dashboard - Lumière</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        body {
            margin:0; min-height:100vh;
            background: radial-gradient(circle at 100% 0%, rgba(0,215,96,0.1), transparent 32%), #050505;
            color:#f5f5f5;
            font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        }
        .page { padding:28px clamp(20px,5vw,72px) 64px; }
        a { color:#00d760; text-decoration:none; font-weight:700; }

        .nav { display:flex; justify-content:space-between; gap:20px; align-items:center; }
        .brand { color:#00d760; font-size:30px; font-weight:900; letter-spacing:-0.05em; text-transform:uppercase; }
        .nav-right { display:flex; gap:12px; align-items:center; }
        .logout {
            border:1px solid rgba(255,255,255,0.13); border-radius:999px;
            padding:10px 18px; background:transparent;
            color:#d1d5db; font:inherit; font-size:14px; font-weight:600; cursor:pointer;
        }
        .logout:hover { background:rgba(255,255,255,0.07); }

        .admin-actions { display:flex; flex-wrap:wrap; gap:10px; margin:0 0 32px; }
        .action-link {
            display:inline-flex; min-height:44px; align-items:center;
            border-radius:999px; padding:0 20px;
            background:#00d760; color:#03130a;
            font-weight:800; font-size:14px; text-decoration:none;
            transition:background 0.15s;
        }
        .action-link:hover { background:#00bf55; color:#03130a; }
        .action-link.secondary {
            background:rgba(255,255,255,0.07);
            border:1px solid rgba(255,255,255,0.13);
            color:#d1d5db;
        }
        .action-link.secondary:hover { background:rgba(255,255,255,0.13); color:white; }

        h1 {
            max-width:900px; margin:56px 0 32px;
            font-size:clamp(44px,7vw,88px);
            line-height:0.92; letter-spacing:-0.06em; text-transform:uppercase; font-weight:900;
        }

        .section-label {
            color:#4b5563; font-size:11px; font-weight:700;
            letter-spacing:0.1em; text-transform:uppercase; margin:0 0 14px;
        }

        .stats {
            display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px;
        }

        .card {
            border:1px solid rgba(255,255,255,0.08);
            border-radius:22px; background:#0d1117; padding:22px 24px;
        }
        .card span { color:#6b7280; font-size:13px; font-weight:500; }
        .card strong {
            display:block; margin-top:10px;
            color:#00d760; font-size:44px; letter-spacing:-0.06em;
            font-weight:900; line-height:1;
        }
        .card.muted strong { color:#d1d5db; }

        .panel {
            border:1px solid rgba(255,255,255,0.08);
            border-radius:22px; background:#0d1117; padding:24px 28px;
            margin-top:18px;
        }
        .panel h2 { margin:0 0 10px; font-size:20px; letter-spacing:-0.03em; font-weight:700; }
        .panel p { max-width:720px; color:#6b7280; line-height:1.7; font-size:14px; margin:0; }

        @media(max-width:900px) { .stats { grid-template-columns:repeat(2, minmax(0,1fr)); } }
        @media(max-width:560px) {
            .nav { align-items:flex-start; flex-direction:column; }
            .stats { grid-template-columns:1fr; }
        }
        .mode-switcher { position:fixed; bottom:24px; right:24px; z-index:999; display:flex; border-radius:999px; border:1px solid rgba(255,255,255,0.1); background:rgba(5,5,5,0.9); backdrop-filter:blur(16px); padding:4px; gap:2px; box-shadow:0 4px 28px rgba(0,0,0,0.5); }
        .mode-btn { border-radius:999px; padding:8px 16px; font-size:13px; font-weight:700; color:#4b5563; text-decoration:none; transition:all 0.15s; white-space:nowrap; }
        .mode-btn.active { background:#00d760; color:#03130a; }
        .mode-btn:hover:not(.active) { color:#d1d5db; }
    </style>
</head>
<body>
    <main class="page">
        <nav class="nav">
            <div class="brand">Admin · Lumière</div>
            <div class="nav-right">
                <form method="POST" action="{{ route('logout') }}">
                    @csrf
                    <button class="logout" type="submit">Đăng xuất</button>
                </form>
            </div>
        </nav>

        <h1>Dashboard quản trị</h1>

        <div class="admin-actions">
            <a class="action-link" href="{{ route('admin.movies.create') }}">+ Upload phim mới</a>
            <a class="action-link secondary" href="{{ route('admin.movies.index') }}">Quản lý phim</a>
            <a class="action-link secondary" href="{{ route('admin.users.index') }}">Quản lý người dùng</a>
            <a class="action-link secondary" href="{{ route('admin.ratings.index') }}">Rating phim</a>
            <a class="action-link secondary" href="{{ route('admin.actors.index') }}">Diễn viên</a>
        </div>

        <p class="section-label">PHIM</p>
        <section class="stats">
            <article class="card">
                <span>Tổng số phim</span>
                <strong>{{ $totalMovies }}</strong>
            </article>
            <article class="card">
                <span>Đang hiển thị</span>
                <strong>{{ $activeMovies }}</strong>
            </article>
            <article class="card muted">
                <span>Bình luận</span>
                <strong>{{ $totalComments }}</strong>
            </article>
            <article class="card muted">
                <span>Lượt đánh giá</span>
                <strong>{{ $totalRatings }}</strong>
            </article>
        </section>

        <p class="section-label" style="margin-top:28px">NGƯỜI DÙNG</p>
        <section class="stats">
            <article class="card">
                <span>Tổng tài khoản</span>
                <strong>{{ $totalUsers }}</strong>
            </article>
            <article class="card">
                <span>Admin</span>
                <strong>{{ $totalAdmins }}</strong>
            </article>
            <article class="card muted">
                <span>Đang hoạt động</span>
                <strong>{{ $activeUsers }}</strong>
            </article>
            <article class="card muted">
                <span>Bị khóa</span>
                <strong>{{ $bannedUsers }}</strong>
            </article>
        </section>

    </main>
    <div class="mode-switcher">
        <a href="{{ route('movies.index') }}" class="mode-btn">Website</a>
        <a href="{{ route('admin.dashboard') }}" class="mode-btn active">Admin</a>
    </div>
</body>
</html>
