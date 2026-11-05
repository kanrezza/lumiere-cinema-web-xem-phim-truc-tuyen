<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Actor;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;
use Illuminate\View\View;

class AdminActorController extends Controller
{
    public function index(): View
    {
        $actors = Actor::latest()->paginate(20);
        return view('admin.actors.index', compact('actors'));
    }

    public function create(): View
    {
        return view('admin.actors.create');
    }

    public function store(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'name'   => 'required|string|max:255',
            'bio'    => 'nullable|string',
            'avatar' => 'nullable|image|max:4096',
        ]);

        if ($request->hasFile('avatar')) {
            $data['avatar'] = $request->file('avatar')->store('actors', 'public');
        }

        Actor::create($data);

        return redirect()->route('admin.actors.index')->with('success', 'Đã thêm diễn viên!');
    }

    public function edit(Actor $actor): View
    {
        return view('admin.actors.edit', compact('actor'));
    }

    public function update(Request $request, Actor $actor): RedirectResponse
    {
        $data = $request->validate([
            'name'   => 'required|string|max:255',
            'bio'    => 'nullable|string',
            'avatar' => 'nullable|image|max:4096',
        ]);

        if ($request->hasFile('avatar')) {
            if ($actor->avatar) {
                Storage::disk('public')->delete($actor->avatar);
            }
            $data['avatar'] = $request->file('avatar')->store('actors', 'public');
        }

        $actor->update($data);

        return redirect()->route('admin.actors.index')->with('success', 'Đã cập nhật diễn viên!');
    }

    public function destroy(Actor $actor): RedirectResponse
    {
        if ($actor->avatar) {
            Storage::disk('public')->delete($actor->avatar);
        }
        $actor->delete();

        return redirect()->route('admin.actors.index')->with('success', 'Đã xóa diễn viên!');
    }
}
