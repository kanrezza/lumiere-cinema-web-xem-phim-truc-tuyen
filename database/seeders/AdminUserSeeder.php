<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class AdminUserSeeder extends Seeder
{
    /**
     * Seed an administrator only when credentials are explicitly configured.
     */
    public function run(): void
    {
        $email = config('seeding.admin.email');
        $password = config('seeding.admin.password');

        if (! is_string($email) || ! is_string($password)
            || ! filter_var(trim($email), FILTER_VALIDATE_EMAIL)
            || mb_strlen(trim($password)) < 12) {
            $this->command?->warn('Bỏ qua tài khoản quản trị: cần ADMIN_EMAIL hợp lệ và ADMIN_PASSWORD tối thiểu 12 ký tự.');

            return;
        }

        User::updateOrCreate(
            ['email' => trim($email)],
            [
                'name' => 'MovieWeb Admin',
                'password' => Hash::make($password),
                'role' => 'admin',
                'status' => 'active',
            ],
        );
    }
}

