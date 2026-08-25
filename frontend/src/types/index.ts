export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Business {
  id: string;
  name: string;
  industry: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}
