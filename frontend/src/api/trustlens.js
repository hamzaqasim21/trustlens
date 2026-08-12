const API_BASE = "http://127.0.0.1:8000"

export async function analyzeProfile(username) {
  const response = await fetch(`${API_BASE}/analyze-live`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  })

  if (!response.ok) {
    throw new Error(`Server error: ${response.status}`)
  }

  const data = await response.json()

  if (data.error) {
    throw new Error(data.error)
  }

  return data
}