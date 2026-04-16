export interface User {
  id: string;
  email: string;
  full_name: string | null;
  plan: 'free' | 'pro' | 'business' | 'enterprise';
  is_active?: boolean;
  is_verified?: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

/** Backend /auth/login and /auth/register response shape. */
export interface TokenPair {
  tokens: Tokens;
  user: User;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}
