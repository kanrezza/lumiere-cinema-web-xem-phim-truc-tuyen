<?php

use App\Http\Controllers\Admin\AdminDashboardController;
use App\Http\Controllers\Admin\AdminMovieController;
use App\Http\Controllers\Admin\AdminActorController;
use App\Http\Controllers\Admin\AdminRatingController;
use App\Http\Controllers\Admin\AdminUserController;
use App\Http\Controllers\Auth\AuthController;
use App\Http\Controllers\CommentController;
use App\Http\Controllers\HistoryController;
use App\Http\Controllers\MovieController;
use App\Http\Controllers\ProfileController;
use App\Http\Controllers\RatingController;
use App\Http\Controllers\TopRatedController;
use App\Http\Controllers\ActorController;
use App\Http\Controllers\WatchlistController;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    $categories = \App\Models\Category::all();
    $query      = trim((string) request('q', ''));
    $catSlug    = request('cat', '');

    $moviesQuery = \App\Models\Movie::with('category')
        ->where('status', 'active')
        ->latest();

    if ($query !== '') {
        $moviesQuery->where(function ($q) use ($query) {
            $q->where('title', 'like', "%{$query}%")
              ->orWhere('type', 'like', "%{$query}%")
              ->orWhereHas('categories', fn ($q) => $q->where('name', 'like', "%{$query}%"))
              ->orWhereHas('category', fn ($q) => $q->where('name', 'like', "%{$query}%"));
        });
    }

    if ($catSlug === 'phim-bo') {
        $moviesQuery->where('type', 'Phim bộ');
    } elseif ($catSlug === 'phim-le') {
        $moviesQuery->where('type', 'Phim lẻ');
    } elseif ($catSlug === 'chieu-rap') {
        $moviesQuery->where('type', 'Chiếu rạp');
    } elseif ($catSlug !== '') {
        $moviesQuery->where(function ($q) use ($catSlug) {
            $q->whereHas('categories', fn ($q) => $q->where('slug', $catSlug))
              ->orWhereHas('category', fn ($q) => $q->where('slug', $catSlug));
        });
    }

    $movies   = $moviesQuery->paginate(12)->withQueryString();
    $featured = ($catSlug !== '' || $query !== '')
        ? $movies->first()
        : \App\Models\Movie::with('category')->where('status', 'active')->latest()->first();

    return view('welcome', compact('categories', 'movies', 'featured', 'query', 'catSlug'));
})->name('home');

Route::middleware('guest')->group(function () {
    Route::get('/login',    [AuthController::class, 'showLogin'])->name('login');
    Route::post('/login',   [AuthController::class, 'login'])->name('login.store');
    Route::get('/register', [AuthController::class, 'showRegister'])->name('register');
    Route::post('/register',[AuthController::class, 'register'])->name('register.store');
});

Route::post('/logout', [AuthController::class, 'logout'])->middleware('auth')->name('logout');

Route::get('/dashboard', function () {
    return request()->user()->role === 'admin'
        ? redirect()->route('admin.dashboard')
        : redirect()->route('movies.index');
})->middleware(['auth', 'active'])->name('dashboard');

// ----- User routes -----
Route::middleware(['auth', 'active'])->group(function () {
    Route::get('/movies',         [MovieController::class, 'index'])->name('movies.index');
    Route::get('/movies/{movie}', [MovieController::class, 'show'])->name('movies.show');

    Route::get('/profile',  [ProfileController::class, 'edit'])->name('profile.edit');
    Route::post('/profile', [ProfileController::class, 'update'])->name('profile.update');

    Route::post('/movies/{movie}/comments',   [CommentController::class, 'store'])->name('comments.store');
    Route::delete('/comments/{comment}',      [CommentController::class, 'destroy'])->name('comments.destroy');

    Route::post('/movies/{movie}/ratings',    [RatingController::class, 'store'])->name('ratings.store');

    Route::get('/top-rated', [TopRatedController::class, 'index'])->name('top-rated.index');

    Route::get('/actors',        [ActorController::class, 'index'])->name('actors.index');
    Route::get('/actors/{name}', [ActorController::class, 'show'])->name('actors.show');

    Route::get('/history',   [HistoryController::class, 'index'])->name('history.index');
    Route::post('/history/clear', [HistoryController::class, 'clear'])->name('history.clear');

    Route::get('/watchlist',              [WatchlistController::class, 'index'])->name('watchlist.index');
    Route::post('/watchlist/{movie}',     [WatchlistController::class, 'toggle'])->name('watchlist.toggle');
});

// ----- Admin routes -----
Route::prefix('admin')->middleware(['auth', 'active', 'admin'])->group(function () {
    Route::get('/dashboard', [AdminDashboardController::class, 'index'])->name('admin.dashboard');

    // Movies CRUD
    Route::get('/movies',                  [AdminMovieController::class, 'index'])->name('admin.movies.index');
    Route::get('/movies/create',           [AdminMovieController::class, 'create'])->name('admin.movies.create');
    Route::post('/movies',                 [AdminMovieController::class, 'store'])->name('admin.movies.store');
    Route::get('/movies/{movie}/edit',     [AdminMovieController::class, 'edit'])->name('admin.movies.edit');
    Route::put('/movies/{movie}',          [AdminMovieController::class, 'update'])->name('admin.movies.update');
    Route::delete('/movies/{movie}',       [AdminMovieController::class, 'destroy'])->name('admin.movies.destroy');

    // User management
    Route::get('/users',                   [AdminUserController::class, 'index'])->name('admin.users.index');
    Route::post('/users/{user}/ban',       [AdminUserController::class, 'ban'])->name('admin.users.ban');
    Route::post('/users/{user}/unban',     [AdminUserController::class, 'unban'])->name('admin.users.unban');

    // Rating management
    Route::get('/ratings',                 [AdminRatingController::class, 'index'])->name('admin.ratings.index');
    Route::delete('/ratings/{rating}',     [AdminRatingController::class, 'destroy'])->name('admin.ratings.destroy');

    // Actor management
    Route::get('/actors',                  [AdminActorController::class, 'index'])->name('admin.actors.index');
    Route::get('/actors/create',           [AdminActorController::class, 'create'])->name('admin.actors.create');
    Route::post('/actors',                 [AdminActorController::class, 'store'])->name('admin.actors.store');
    Route::get('/actors/{actor}/edit',     [AdminActorController::class, 'edit'])->name('admin.actors.edit');
    Route::put('/actors/{actor}',          [AdminActorController::class, 'update'])->name('admin.actors.update');
    Route::delete('/actors/{actor}',       [AdminActorController::class, 'destroy'])->name('admin.actors.destroy');
});
