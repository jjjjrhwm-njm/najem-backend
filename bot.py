from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# مفتاحك الذي استخرجته للتو
TMDB_API_KEY = "4765acb8727abd98a0ef375f4f2ec8bf"

@app.route('/get-drama', methods=['GET'])
def get_automated_drama():
    # جلب المسلسلات الصينية الأكثر شهرة (لغة zh) من TMDB
    tmdb_url = f"https://api.themoviedb.org/3/discover/tv?api_key={TMDB_API_KEY}&with_original_language=zh&sort_by=popularity.desc"
    
    try:
        response = requests.get(tmdb_url)
        data = response.json()
        
        library = []
        for item in data.get('results', []):
            library.append({
                "title": item.get('name') or item.get('original_name'),
                "poster": f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}",
                "episodes": [
                    # السيرفرات العالمية التي تبحث عن الحلقة تلقائياً
                    {"name": "سيرفر رئيسي", "url": f"https://vidsrc.to/embed/tv/{item.get('id')}/1/1"},
                    {"name": "سيرفر احتياطي", "url": f"https://embed.su/embed/tv/{item.get('id')}/1/1"}
                ]
            })
        return jsonify(library)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
