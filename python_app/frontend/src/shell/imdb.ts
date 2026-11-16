export function imdbRating(id = '', rating = '') {
  const score = Number(rating)
  if (!/^tt[0-9]{7,10}$/.test(id) || !/^[0-9]+(?:\.[0-9])?$/.test(rating) || score < 1 || score > 10) return
  return {
    url: `https://www.imdb.com/title/${id}/`,
    score: score.toLocaleString('vi-VN', {minimumFractionDigits: 1, maximumFractionDigits: 1}),
  }
}
