<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Quản lý diễn viên - Admin</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        body { margin:0; min-height:100vh; background:radial-gradient(circle at 100% 0%,rgba(0,215,96,0.1),transparent 32%),#050505; color:#f5f5f5; font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
        .page { padding:28px clamp(20px,5vw,72px) 64px; }
        a { color:#00d760; text-decoration:none; font-weight:700; }
        .nav { display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap; }
        .brand { color:#00d760; font-size:28px; font-weight:900; letter-spacing:-0.05em; text-transform:uppercase; }
        h1 { margin:48px 0 6px; font-size:clamp(36px,6vw,68px); line-height:0.93; letter-spacing:-0.05em; text-transform:uppercase; font-weight:900; }
        .btn { display:inline-flex; align-items:center; min-height:42px; border-radius:999px; padding:0 18px; font:inherit; font-weight:700; cursor:pointer; border:0; text-decoration:none; font-size:14px; }
        .btn-green { background:#00d760; color:#03130a; }
        .btn-green:hover { background:#00bf55; }
        .btn-outline { background:transparent; border:1px solid rgba(255,255,255,0.15); color:#d1d5db; }
        .btn-outline:hover { background:rgba(255,255,255,0.07); }
        .btn-sm { font-size:13px; min-height:34px; padding:0 12px; border-radius:8px; }
        .alert-success { border:1px solid rgba(0,215,96,0.38); border-radius:14px; padding:12px 16px; background:rgba(0,215,96,0.08); color:#bbf7d0; margin-bottom:20px; font-size:14px; }
        .toolbar { display:flex; flex-wrap:wrap; gap:12px; margin:20px 0; align-items:center; }
        .table-wrap { overflow-x:auto; }
        table { width:100%; border-collapse:collapse; min-width:600px; }
        thead th { border-bottom:1px solid rgba(255,255,255,0.09); padding:10px 14px; text-align:left; color:#6b7280; font-size:11px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; }
        tbody tr { border-bottom:1px solid rgba(255,255,255,0.05); }
        tbody tr:hover { background:rgba(255,255,255,0.03); }
        tbody td { padding:13px 14px; font-size:14px; vertical-align:middle; }
        .actor-avatar-img { width:46px; height:46px; border-radius:999px; object-fit:cover; border:1px solid rgba(255,255,255,0.1); }
        .actor-avatar-placeholder { width:46px; height:46px; border-radius:999px; background:rgba(0,215,96,0.12); border:1px solid rgba(0,215,96,0.3); display:grid; place-items:center; font-size:18px; font-weight:900; color:#00d760; }
        .bio-preview { color:#6b7280; font-size:13px; max-width:360px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .actions { display:flex; gap:8px; }
        .pagination { display:flex; justify-content:center; gap:8px; margin-top:32px; flex-wrap:wrap; }
        .pagination a, .pagination span { min-width:38px; height:38px; display:grid; place-items:center; border:1px solid rgba(255,255,255,0.1); border-radius:8px; background:rgba(255,255,255,0.04); color:#9ca3af; font-size:14px; font-weight:700; }
        .pagination a:hover { border-color:#00d760; color:#00d760; }
        .pagination .active span { border-color:#00d760; background:rgba(0,215,96,0.14); color:#00d760; }
        .pagination .disabled span { opacity:0.35; }
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
            <div style="display:flex;gap:10px;flex-wrap:wrap">
                <a class="btn btn-outline btn-sm" href="{{ route('admin.dashboard') }}">← Dashboard</a>
                <form method="POST" action="{{ route('logout') }}">
                    @csrf
                    <button class="btn btn-outline btn-sm" type="submit">Đăng xuất</button>
                </form>
            </div>
        </nav>

        <h1>Diễn viên</h1>

        @if(session('success'))
            <div class="alert-success">{{ session('success') }}</div>
        @endif

        <div class="toolbar">
            <a class="btn btn-green" href="{{ route('admin.actors.create') }}">+ Thêm diễn viên</a>
            <span style="color:#6b7280;font-size:14px;font-weight:500">Tổng {{ $actors->total() }} diễn viên</span>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th style="width:60px">Ảnh</th>
                        <th>Tên diễn viên</th>
                        <th>Giới thiệu</th>
                        <th style="width:130px">Hành động</th>
                    </tr>
                </thead>
                <tbody>
                    @forelse($actors as $actor)
                        <tr>
                            <td>
                                @if($actor->avatar)
                                    <img class="actor-avatar-img" src="{{ $actor->avatarUrl() }}" alt="{{ $actor->name }}" onerror="this.style.display='none'">
                                @else
                                    <div class="actor-avatar-placeholder">{{ mb_strtoupper(mb_substr($actor->name, 0, 1)) }}</div>
                                @endif
                            </td>
                            <td style="font-weight:700;color:#f3f4f6">{{ $actor->name }}</td>
                            <td>
                                @if($actor->bio)
                                    <div class="bio-preview">{{ $actor->bio }}</div>
                                @else
                                    <span style="color:#374151">—</span>
                                @endif
                            </td>
                            <td>
                                <div class="actions">
                                    <a class="btn btn-outline btn-sm" href="{{ route('admin.actors.edit', $actor) }}">Sửa</a>
                                    <form method="POST" action="{{ route('admin.actors.destroy', $actor) }}">
                                        @csrf @method('DELETE')
                                        <button class="btn btn-sm" style="background:rgba(239,68,68,0.14);color:#ef4444;border:1px solid rgba(239,68,68,0.24)" type="submit" onclick="return confirm('Xóa diễn viên {{ addslashes($actor->name) }}?')">Xóa</button>
                                    </form>
                                </div>
                            </td>
                        </tr>
                    @empty
                        <tr>
                            <td colspan="4" style="text-align:center;color:#4b5563;padding:52px;font-size:15px">Chưa có diễn viên nào.</td>
                        </tr>
                    @endforelse
                </tbody>
            </table>
        </div>

        @if($actors->hasPages())
            <div class="pagination">
                @foreach($actors->links()->elements as $element)
                    @if(is_string($element))<span class="disabled"><span>{{ $element }}</span></span>@endif
                    @if(is_array($element))
                        @foreach($element as $page => $url)
                            @if($page == $actors->currentPage())
                                <span class="active"><span>{{ $page }}</span></span>
                            @else
                                <a href="{{ $url }}">{{ $page }}</a>
                            @endif
                        @endforeach
                    @endif
                @endforeach
                @if($actors->hasNextPage())<a href="{{ $actors->nextPageUrl() }}">›</a>@endif
            </div>
        @endif
    </main>

    <div class="mode-switcher">
        <a href="/movies" class="mode-btn">Website</a>
        <a href="/admin/dashboard" class="mode-btn active">Admin</a>
    </div>
</body>
</html>
