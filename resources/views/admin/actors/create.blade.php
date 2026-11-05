<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Thêm diễn viên - Admin</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        body { margin:0; min-height:100vh; background:radial-gradient(circle at 100% 0%,rgba(0,215,96,0.1),transparent 32%),#050505; color:#f5f5f5; font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; }
        .page { padding:28px clamp(20px,5vw,72px) 64px; max-width:760px; }
        a { color:#00d760; text-decoration:none; font-weight:700; }
        .nav { display:flex; justify-content:space-between; gap:16px; align-items:center; flex-wrap:wrap; }
        .brand { color:#00d760; font-size:28px; font-weight:900; letter-spacing:-0.05em; text-transform:uppercase; }
        h1 { margin:48px 0 32px; font-size:clamp(30px,5vw,52px); line-height:0.93; letter-spacing:-0.05em; text-transform:uppercase; font-weight:900; }
        .btn { display:inline-flex; align-items:center; min-height:42px; border-radius:999px; padding:0 18px; font:inherit; font-weight:700; cursor:pointer; border:0; text-decoration:none; font-size:14px; }
        .btn-green { background:#00d760; color:#03130a; }
        .btn-green:hover { background:#00bf55; }
        .btn-outline { background:transparent; border:1px solid rgba(255,255,255,0.15); color:#d1d5db; }
        .btn-outline:hover { background:rgba(255,255,255,0.07); }
        .btn-sm { font-size:13px; min-height:34px; padding:0 12px; border-radius:8px; }
        .form-group { margin-bottom:22px; }
        label { display:block; font-size:13px; font-weight:700; color:#9ca3af; letter-spacing:0.05em; text-transform:uppercase; margin-bottom:8px; }
        input[type=text], textarea {
            width:100%; border:1px solid rgba(255,255,255,0.12); border-radius:12px;
            padding:12px 14px; background:rgba(255,255,255,0.06); color:#f5f5f5;
            font:inherit; font-size:14px; outline:none; box-sizing:border-box;
        }
        input[type=text]:focus, textarea:focus { border-color:#00d760; }
        textarea { resize:vertical; min-height:120px; }
        input[type=file] { display:block; font-size:14px; color:#9ca3af; margin-top:4px; }
        .avatar-preview { width:100px; height:100px; border-radius:999px; object-fit:cover; border:2px solid rgba(0,215,96,0.35); margin-bottom:10px; display:none; }
        .error { color:#f87171; font-size:13px; margin-top:6px; }
        .form-actions { display:flex; gap:12px; margin-top:32px; }
    </style>
</head>
<body>
    <main class="page">
        <nav class="nav">
            <div class="brand">Admin · Lumière</div>
            <div style="display:flex;gap:10px;flex-wrap:wrap">
                <a class="btn btn-outline btn-sm" href="{{ route('admin.actors.index') }}">← Diễn viên</a>
                <a class="btn btn-outline btn-sm" href="{{ route('admin.dashboard') }}">Dashboard</a>
            </div>
        </nav>

        <h1>Thêm diễn viên</h1>

        <form method="POST" action="{{ route('admin.actors.store') }}" enctype="multipart/form-data">
            @csrf

            <div class="form-group">
                <label>Tên diễn viên *</label>
                <input type="text" name="name" value="{{ old('name') }}" placeholder="Ví dụ: Tom Hanks" required>
                @error('name')<div class="error">{{ $message }}</div>@enderror
            </div>

            <div class="form-group">
                <label>Ảnh đại diện</label>
                <img id="preview" class="avatar-preview" src="" alt="preview">
                <input type="file" name="avatar" accept="image/*" onchange="previewImg(this)">
                <div style="color:#6b7280;font-size:12px;margin-top:6px">JPG, PNG, WebP — tối đa 4MB</div>
                @error('avatar')<div class="error">{{ $message }}</div>@enderror
            </div>

            <div class="form-group">
                <label>Giới thiệu</label>
                <textarea name="bio" placeholder="Tiểu sử, thông tin về diễn viên...">{{ old('bio') }}</textarea>
                @error('bio')<div class="error">{{ $message }}</div>@enderror
            </div>

            <div class="form-actions">
                <button class="btn btn-green" type="submit">Thêm diễn viên</button>
                <a class="btn btn-outline" href="{{ route('admin.actors.index') }}">Hủy</a>
            </div>
        </form>
    </main>

    <script>
        function previewImg(input) {
            const preview = document.getElementById('preview');
            if (input.files && input.files[0]) {
                const reader = new FileReader();
                reader.onload = e => { preview.src = e.target.result; preview.style.display = 'block'; };
                reader.readAsDataURL(input.files[0]);
            }
        }
    </script>
</body>
</html>
