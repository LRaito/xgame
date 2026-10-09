const USERNAME_KEY = "x_username";
const CLEAR_KEYS = [USERNAME_KEY];

export function getUsername() {
    return sessionStorage.getItem(USERNAME_KEY) || "";
}

export function setUsername(username) {
    if (username) {
        sessionStorage.setItem(USERNAME_KEY, username);
    } else {
        sessionStorage.removeItem(USERNAME_KEY);
    }
}

export function clearSession() {
    CLEAR_KEYS.forEach((key) => {
        sessionStorage.removeItem(key);
        localStorage.removeItem(key);
    });
}
