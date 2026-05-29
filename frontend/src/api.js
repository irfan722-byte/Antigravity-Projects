const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = {
  // Save JWT
  setToken(token) {
    localStorage.setItem("token", token);
  },
  
  getToken() {
    return localStorage.getItem("token");
  },
  
  logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  },

  // Helper fetch method
  async request(path, options = {}) {
    const token = this.getToken();
    const headers = {
      ...(options.headers || {}),
    };
    
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
    
    if (response.status === 401) {
      this.logout();
      if (!window.location.hash.includes("#/login")) {
        window.location.href = "/#/login";
      }
    }
    
    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: "An error occurred" }));
      throw new Error(errData.detail || "Request failed");
    }
    
    return response.json();
  },

  // Auth endpoints
  async signup(firebaseToken, fullName) {
    const formData = new FormData();
    formData.append("firebase_token", firebaseToken);
    formData.append("full_name", fullName);
    
    return this.request("/auth/signup", {
      method: "POST",
      body: formData,
    });
  },

  async login(firebaseToken) {
    const formData = new FormData();
    formData.append("firebase_token", firebaseToken);
    
    const data = await this.request("/auth/login", {
      method: "POST",
      body: formData,
    });
    
    if (data.access_token) {
      this.setToken(data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
    }
    
    return data;
  },
  
  async getMe() {
    return this.request("/users/me");
  },

  // Tasks endpoints
  async getActiveTask() {
    return this.request("/tasks/active");
  },
  
  getDownloadUrl(taskId) {
    return `${API_BASE}/tasks/${taskId}/download`;
  },
  
  async submitTask(taskId, file) {
    const formData = new FormData();
    formData.append("file", file);
    
    return this.request(`/tasks/${taskId}/submit`, {
      method: "POST",
      body: formData,
    });
  },

  // Leaderboard & announcements
  async getLeaderboard() {
    return this.request("/leaderboard");
  },
  
  async getAnnouncements() {
    return this.request("/announcements");
  },

  // Admin endpoints
  async getAdminMetrics() {
    return this.request("/admin/metrics");
  },
  
  async getAdminUsersProgress() {
    return this.request("/admin/users-progress");
  },
  
  async postAnnouncement(content) {
    const formData = new FormData();
    formData.append("content", content);
    
    return this.request("/admin/announcement", {
      method: "POST",
      body: formData,
    });
  },
  
  async uploadTask(taskData, file) {
    const formData = new FormData();
    formData.append("id", taskData.id);
    formData.append("stage", taskData.stage);
    formData.append("title", taskData.title);
    formData.append("scenario_text", taskData.scenario_text);
    formData.append("validations_json", JSON.stringify(taskData.validations));
    if (file) {
      formData.append("file", file);
    }
    
    return this.request("/admin/upload-task", {
      method: "POST",
      body: formData,
    });
  }
};
