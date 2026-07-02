export const PASSWORD_REQUIREMENTS_HINT =
  "At least 8 characters with an uppercase letter, lowercase letter, number, and special character (e.g. RajAgro1!).";

export function validatePasswordStrength(password: string): string | null {
  const failures: string[] = [];
  if (password.length < 8) failures.push("at least 8 characters");
  if (!/[A-Z]/.test(password)) failures.push("one uppercase letter (A–Z)");
  if (!/[a-z]/.test(password)) failures.push("one lowercase letter (a–z)");
  if (!/\d/.test(password)) failures.push("one digit (0–9)");
  if (!/[^A-Za-z0-9]/.test(password)) failures.push("one special character (e.g. !@#$%^&*)");
  if (failures.length === 0) return null;
  return `Password must include: ${failures.join("; ")}.`;
}
