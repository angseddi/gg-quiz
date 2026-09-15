import streamlit as st
from streamlit_autorefresh import st_autorefresh

# 1. 2초마다 화면 자동 새로고침 (실시간 효과)
st_autorefresh(interval=2000, key="quiz_refresh")

# 2. 메인 타이틀
st.title("n/n Case Review 퀴즈쇼")

# 3. 방 선택 및 역할 분리 (간단한 예시)
role = st.sidebar.radio("접속 권한", ["참가자(Player)", "출제자(Host)"])

if role == "출제자(Host)":
    pwd = st.sidebar.text_input("출제자 비밀번호", type="password")
    if pwd == "1234": # 실제론 DB와 대조
        st.subheader("출제자 컨트롤 패널")
        if st.button("퀴즈쇼 시작!"):
            st.success("참가자들의 화면이 1번 문제로 바뀝니다!")
            # 여기에 DB의 상태를 '시작됨'으로 바꾸는 코드 작성

elif role == "참가자(Player)":
    st.subheader("대기실")
    st.write("출제자가 퀴즈쇼를 시작할 때까지 대기해주세요...")
    # DB 상태를 확인해서 '시작됨'이면 문제 화면을 보여주는 코드 작성
