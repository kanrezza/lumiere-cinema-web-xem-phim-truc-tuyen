<?php

namespace App\Http\Controllers;

use App\Models\Actor;
use App\Models\Category;
use App\Models\Movie;
use Illuminate\View\View;

class ActorController extends Controller
{
    public function index(): View
    {
        $movies = Movie::where('status', 'active')
            ->whereNotNull('actors')
            ->where('actors', '!=', '')
            ->get(['actors']);

        $actorCounts = collect();
        foreach ($movies as $movie) {
            $names = array_map('trim', explode(',', $movie->actors));
            foreach ($names as $name) {
                if ($name !== '') {
                    $actorCounts->push($name);
                }
            }
        }

        $actorCounts = $actorCounts->filter()
            ->countBy()
            ->sortByDesc(fn ($count) => $count);

        // Lấy profile từ bảng actors (nếu có)
        $profiles = Actor::whereIn('name', $actorCounts->keys())->get()->keyBy('name');

        $actors = $actorCounts->map(fn ($count, $name) => [
            'name'    => $name,
            'count'   => $count,
            'profile' => $profiles->get($name),
        ]);

        $categories = Category::all();
        return view('actors.index', compact('actors', 'categories'));
    }

    public function show(string $name): View
    {
        $movies = Movie::with('category')
            ->where('status', 'active')
            ->where('actors', 'like', '%' . $name . '%')
            ->latest()
            ->get();

        $profile    = Actor::where('name', $name)->first();
        $categories = Category::all();

        return view('actors.show', compact('name', 'movies', 'categories', 'profile'));
    }
}
