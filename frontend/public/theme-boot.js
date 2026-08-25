(() => {
  let theme = "light";
  try {
    if (localStorage.getItem("localflow-theme") === "dark") theme = "dark";
  } catch {
    // Storage can be unavailable in privacy modes; the light default remains valid.
  }
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themeGuard = theme;
})();
