import re
import os
import requests
import pymongo
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from collections import Counter
from pykospacing import Spacing
from soynlp.word import WordExtractor
from soynlp.tokenizer import LTokenizer
from konlpy.tag import Kkma


class TwentyNineScraper:
    def __init__(self):
        self.driver = None
        self.load_webdriver()
        load_dotenv()
        self.password = os.getenv("MONGODB_PASSWORD")
        self.connect_to_mongodb()

        self.spacing = Spacing()     # PyKoSpacing 인스턴스 생성
        word_extractor = WordExtractor()    # WordExtractor 인스턴스 생성
        
        # 토크나이저 생성
        word_scores = word_extractor.word_scores()
        self.tokenizer = LTokenizer(scores=word_scores)        
        
        # 키워드 셋
        keyword_file = os.path.join("keyword", "keyword.txt")
        with open(keyword_file, 'r', encoding='utf-8') as file:
            self.keyword_data = [line.strip() for line in file]

        # 불용어 셋
        stopword_file = os.path.join("keyword", "stopword.txt")
        with open(stopword_file, 'r', encoding='utf-8') as file:
            self.stopword_data = [line.strip() for line in file]


    # 크롬 웹드라이버 초기화
    def load_webdriver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=chrome_options)


    # 웹드라이버 종료
    def close_webdriver(self):
        if self.driver:
            self.driver.quit()


    # 상품 전체 리스트
    def get_twentyninecm_products_list(self, categoryLargeCode, categoryMediumCode, categorySmallCode, mainCategory, subCategory):
        print(f"{subCategory}")
        url = 'https://search-api.29cm.co.kr/api/v4/products/category/'
        params = {
            'categoryLargeCode': categoryLargeCode,
            'categoryMediumCode': categoryMediumCode,
            'categorySmallCode': categorySmallCode,
            'count': 2,
            'page': 1,
            'sort': 'latest',
            'init': 'T',
            'excludeSoldOut': False,
        }

        # 카테고리별로 상품 2개만 조회 후 res의 productsTotalCount를 저장
        response = requests.get(url, params=params)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'Other error occurred: {err}')
            return
        
        results = response.json()
        params['count'] = results.get('data', {}).get('productsTotalCount', 0)

        # 전체 상품 조회
        response = requests.get(url, params=params)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(f"HTTP Error: {err}")

        results = response.json()

        # 상품 리스트
        products = results.get('data', {}).get('products', [])

        for product in products[:50]:
            itemNo = product.get('itemNo', None)

            # 이미 저장된 상품인지 확인
            if self.check_if_product_in_mongodb(itemNo):
                continue

            reviewCount = product.get('reviewCount', None)
            print(f"{subCategory}({itemNo}) crawing...")

            # 상품 상세 정보 크롤링
            detail_info = self.crawling_twentyninecm_product_info(itemNo)
            # 5000개 이상의 리뷰를 한 번에 가져올 시 500 에러 발생하기 때문에 5000개 이하로 가져옴
            product_reviews, review_string = self.get_twentyninecm_reviews_list(itemNo, reviewCount)

            # 상품 정보가 없는 경우
            if not detail_info:
                continue

            # categoryLargeCode가 272000000 이상이면 여성 상품
            gender = 'female'
            if (categoryLargeCode // 1000000) >= 272:
                gender = 'male'

            product_info = {
                'product_id': itemNo,
                'mall_name': '29cm',
                'main_category': mainCategory,
                'sub_category': subCategory,
                'gender': gender,
                'name': product.get('itemName', None),
                'price': product.get('consumerPrice', None),
                'brand_name': product.get('frontBrandNameKor', None),
                'image': f"https://img.29cm.co.kr/{product.get('imageUrl', None)}",
                'url': f"https://product.29cm.co.kr/catalog/{itemNo}",
                'color': detail_info['color'],
                'size': detail_info['size'],
                'detail_images': detail_info['detail_images'],
                'detail_html': detail_info['detail_html'],
                'reviews': product_reviews,
            }
            
            if review_string:
                keywords, keywords_top5 = self.review_preprocessing(review_string)
                product_info['keywords'] = keywords
                product_info['keywords_top5'] = keywords_top5

            self.save_to_mongodb(product_info)


    # 상품 하나의 디테일 정보 크롤링
    def crawling_twentyninecm_product_info(self, itemNo):
        detail_info = {'color': [], 'size': [], 'detail_images': [], 'detail_html': ''}
        url = f'https://product.29cm.co.kr/catalog/{itemNo}'

        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'Other error occurred: {err}')
            return

        self.driver.implicitly_wait(10)

        try:
            self.driver.get(url)
        except:
            return

        # color 및 size 옵션 입력 요소 찾기
        i = 0
        while True:
            try:
                i += 1
                # dropdown 요소를 찾아 클릭
                option_selector = f'div.css-129gw94.e1yaqq956 > div > div:nth-child({i}) > div > input'
                option_element = self.driver.find_element(By.CSS_SELECTOR, option_selector)
                option_element.click()

                # dropdown ul태그의 li 요소 리스트를 찾음
                ul_selector = 'ul.css-1sxz8vl.e15gsm0h4'
                ul_element = self.driver.find_element(By.CSS_SELECTOR, ul_selector)
                li_elements = ul_element.find_elements(By.TAG_NAME, 'li')

                # 첫 번째 요소는 옵션명
                option_name = li_elements[0].text.lower()

                option_mapping = {'컬러': 'color', '사이즈': 'size'}
                if option_name in option_mapping:
                    option_name = option_mapping[option_name]

                # 옵션 목록을 text로 변환한 후 저장
                option_values = list(map(lambda x: x.text, li_elements[1:]))
                if option_name in ('color', 'size'):
                    detail_info[option_name] = option_values

                elif option_name == 'color:size':
                    color_set = set()
                    size_set = set()

                    for option_value in option_values:
                        color, size = option_value.split(':')
                        color_set.add(color)
                        size_set.add(size)
                        
                    detail_info['color'] = list(color_set)
                    detail_info['size'] = list(size_set)

                elif 'color' in option_name:
                    detail_info['color'] = option_values
                else:
                    pass

                # 색상일 경우 옵션 선택 - 색상을 선택해야 사이즈가 나오기 때문 (품절이 아닌 것)
                if option_name == 'color':
                    j = 1
                    while j < len(detail_info['color']):
                        if '품절' in li_elements[j].text:
                            j += 1
                            continue
                        else:
                            li_elements[j].click()
                else:
                    # dropdown 닫음
                    option_element.click()
            # 요소가 더이상 없는 경우
            except:
                break

        # 상품 상세 정보 더보기 버튼 클릭
        detail_button_selector = 'button.efgb0b60.css-h7utre.e12h9sp60'
        try:
            detail_button_element = self.driver.find_element(By.CSS_SELECTOR, detail_button_selector)
            detail_button_element.click()
        except:
            return

        # 상품 상세 정보를 포함하는 div 요소를 찾음
        detail_selector = 'div.e1jr1djm0.css-1wvn7e9.e1esfft0'
        try:
            detail_element = self.driver.find_element(By.CSS_SELECTOR, detail_selector)
            # 상품 상세 정보 HTML을 가져옴
            detail_info['detail_html'] = detail_element.get_attribute("innerHTML")

            # BeautifulSoup을 사용하여 HTML을 파싱
            soup = BeautifulSoup(detail_info['detail_html'], 'html.parser')

            # img 태그를 찾아서 이미지 URL을 추출하고 product_images에 추가
            img_tags = soup.find_all('img')
            for img_tag in img_tags:
                img_src = img_tag.get('src')
                if img_src:
                    detail_info['detail_images'].append(img_src)
        except:
            return

        return detail_info


    # 리뷰 목록
    def get_twentyninecm_reviews_list(self, itemNo, reviewCount):
        url = 'https://review-api.29cm.co.kr/api/v4/reviews/'
        params = {
            'itemId': itemNo,
            'page': 0,
            'size': reviewCount,
        }

        response = requests.get(url, params=params)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            return {
                'count': 0,
                'average_point': 0,
                'reviews': []
            }, ''
        
        results = response.json()
        reviews = results.get('data', {})

        product_reviews = {
            'count': reviewCount,
            'average_point': reviews.get('averagePoint', 0),
            'reviews': []
        }

        review_string = ''

        for review in reviews.get('results', []):
            # 리뷰 이미지 url 리스트
            images = []
            for file in review.get('uploadFiles', []):
                images.append(f"https://img.29cm.co.kr/{file.get('url', None)}")

            # 상품 옵션
            product_option = []
            for option in review.get('optionValue', []):
                # 색상과 사이즈 정보 추출
                matches = re.findall(r'\[(.*?)\]', option)

                color = matches[0] if matches else None
                size = matches[1] if len(matches) > 1 else None

                # 색상과 사이즈 정보를 option 딕셔너리에 할당
                product_option.append({'color': color, 'size': size})

            user_size = {'height': None, 'weight': None }

            for size in review.get('userSize', []):
                if 'cm' in size:
                    user_size['height'] = size
                else:
                    user_size['weight'] = size

            product_reviews['reviews'].append({
                'contents': review.get('contents', None),
                'created_at': review.get('insertTimestamp', None),
                'images': images,
                'point': review.get('point', None),
                'product_option': product_option,
                'user_size': user_size
            })

            review_string += f" {review.get('contents', None)}"

        return product_reviews, review_string


    def review_preprocessing(self, corpus):
        keywords = {}

        # 전처리 및 토큰화
        corpus = re.sub(r'[^가-힣]+', ' ', corpus)
        corpus = self.spacing(corpus)
        tokens = self.tokenizer.tokenize(corpus)

        for token in tokens:
            # 불용어 제거
            if token in self.stopword_data:
                continue
            
            for keyword in self.keyword_data:
                # 키워드 셋에 있는 단어와 유사성 판별 (토큰 생성하는 데 개당 3초 내외로 걸림)
                # if compare_word_meaning(morphs1, morphs2):

                # 키워드 포함 여부 확인
                if keyword in token:
                    keyword_count = keywords.setdefault(keyword, 0) + 1
                    keywords[keyword] = keyword_count
                    break
        
        # counter 객체 생성
        counter = Counter(keywords)

        # 빈도수가 높은 5개의 키워드 추출
        keywords_top5 = [key for key, _ in counter.most_common(5)]

        return list(keywords.keys()), keywords_top5


    # MongoDB 연결
    def connect_to_mongodb(self):
        self.client = pymongo.MongoClient(f"mongodb+srv://root:{self.password}@cluster0.stojj99.mongodb.net/"
                                          f"?retryWrites=true&w=majority&appName=Cluster")
        self.db = self.client["products"]
        self.collection = self.db["products"]


    # MongoDB 데이터 저장
    def save_to_mongodb(self, product_info):
        try:
            self.collection.insert_one(product_info)
            print("상품 정보가 MongoDB에 성공적으로 저장되었습니다!")
        except Exception as e:
            print(f"MongoDB에 저장하는 중 오류가 발생했습니다: {e}")


    # MongoDB에 이미 저장된 데이터인지 확인
    def check_if_product_in_mongodb(self, product_id):
        result = self.collection.find_one({'product_id': product_id})
        return result is not None