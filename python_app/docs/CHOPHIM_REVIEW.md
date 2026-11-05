# Khảo sát Chợ Phim và định hướng cải thiện Lumière

Đợt khảo sát: **05–06/11/2026**. Website tham khảo: [Chợ Phim](https://chophim.lat/).

## Phạm vi kiểm chứng

Website đã mở được trực tiếp trong trình duyệt. Những quan sát dưới đây đến từ phiên duyệt giao diện công khai khi chưa đăng nhập, bao gồm nhập tìm kiếm, mở danh mục, trang chi tiết và đường dẫn sang giao diện xem. Hai dịch vụ đọc web riêng không tải được trang chủ; điều đó không có nghĩa website ngừng hoạt động.

Không đăng ký tài khoản, thanh toán, gửi bình luận, quét bảo mật hoặc phát/tải phim đầy đủ. Các luồng tài khoản, VIP, thư viện cá nhân, đồng bộ nhiều người và chất lượng phát video của Chợ Phim **chưa được kiểm chứng**. Một mục hiển thị trong giao diện chỉ xác nhận sự hiện diện của mục đó; không tự chứng minh hoạt động phía sau.

## Những gì đã quan sát và thao tác

### Khám phá và tìm kiếm

Trang chủ có điều hướng phim lẻ, phim bộ, TV Shows; dropdown thể loại/quốc gia; mục Thêm dẫn đến diễn viên và lịch chiếu. Ô tìm kiếm có gợi ý tìm phim hoặc diễn viên. Hero có 13 slide, tên Việt/tên gốc, điểm TMDb, năm, tập và thể loại. Chưa xác minh nguồn hoặc độ đúng của điểm số và toàn bộ thao tác chuyển slide. [Trang chủ Chợ Phim](https://chophim.lat/).

Đã nhập **“Mùi Phở”**, nhấn Enter và chờ dữ liệu tải xong: trang kết quả trả **một phim**, dẫn đến `/phim/mui-pho`. Đây là một ca tìm theo tên có dấu đã thực hiện; chưa đủ để kết luận tìm không dấu, tìm theo diễn viên hoặc gợi ý tức thời đều hoạt động. [Kết quả tìm Mùi Phở](https://chophim.lat/tim-kiem?keyword=M%C3%B9i%20Ph%E1%BB%9F), [trang phim](https://chophim.lat/phim/mui-pho).

Trang chủ có hàng phim Hàn Quốc, Trung Quốc, Âu Mỹ; lối vào phim song ngữ; các tuyển tập như Hàn Quốc chữa lành, cổ trang, thanh xuân và anime. Đây là hướng biên tập thư viện đáng tham khảo, khác với việc mặc định tuyên bố có thuật toán đề xuất cá nhân hóa. [Trang chủ](https://chophim.lat/), [chủ đề](https://chophim.lat/chu-de), [phim song ngữ](https://chophim.lat/phim-song-ngu).

### Phim sắp chiếu, chiếu rạp và trailer

Danh mục `/phim-sap-chieu` sau khi tải dữ liệu có tiêu đề **Phim Việt Sắp Chiếu**, 16 card ở trang đầu và điều hướng trang 1/2. Trong đó có cả nhãn **Sắp chiếu** và **PĐ. Full/LT. Full**. Vì vậy, không thể coi danh mục này là một bộ lọc nghiêm ngặt chỉ gồm phim chưa có bản đầy đủ. Trang chủ còn có hàng phim chiếu rạp; sự hiện diện của hàng này chưa xác nhận lịch chiếu thực tế ngoài rạp. [Phim sắp chiếu](https://chophim.lat/phim-sap-chieu), [trang chủ](https://chophim.lat/).

Đã mở trực tiếp danh mục **Phim Chiếu Rạp**: trang đầu có 16 card, phân trang 1/40, các nhãn Full và nhiều phiên bản PĐ/TM/LT. Quan sát này xác nhận cách phân loại thư viện và các nhãn phiên bản; không chứng minh những phim đó đang chiếu tại rạp hoặc các phiên bản đều phát được. [Danh mục Phim Chiếu Rạp](https://chophim.lat/phim-chieu-rap).

Trang **Một thời ta đã yêu** hiển thị FHD, Vietsub, Trailer; trạng thái Trailer và Sắp chiếu; năm 2026, quốc gia Việt Nam và đạo diễn. Có các mục Tập, Gallery, Diễn viên, Đề xuất và bình luận với lựa chọn mới nhất/nổi bật. Khu vực bình luận yêu cầu đăng nhập. Chưa xác minh đúng sai của metadata hoặc hành vi sắp xếp bình luận. [Trang chi tiết Một thời ta đã yêu](https://chophim.lat/phim/mot-thoi-ta-da-yeu).

Phần **Các bản chiếu** có nút **Xem bản này**, dẫn sang route `/xem/`. Sau khi giao diện tải dữ liệu xong, phần chính ghi **Sắp chiếu: Trailer**, metadata **Phần 1/Trailer**, một mục tập mang tên phim với nhãn **Đang phát**. Như vậy, route xem chung có thể phục vụ trailer; chưa có cơ sở coi đây là lỗi cấp bản đầy đủ. Tuy nhiên, nút “Xem bản này” ít rõ nghĩa hơn “Xem trailer”. Lumière chọn đường dẫn trailer riêng và CTA theo nội dung có thật. [Giao diện xem được liên kết từ trang phim](https://chophim.lat/xem/mot-thoi-ta-da-yeu#tap=episode-1&sv=Vietsub+%231&channel=0&server_id=0).

Giao diện xem còn có Auto skip intro ở trạng thái OFF, ánh sáng môi trường, cài đặt, báo lỗi, danh sách tập/server Vietsub #1, diễn viên/vai và đề xuất. DOM của trang chính có một iframe, không có phần tử video trực tiếp; chưa kiểm tra nội dung trong iframe. **Không nhấn phát**, nên nhãn “Đang phát” và sự hiện diện của các điều khiển không chứng minh phát thành công, tự bỏ intro hoặc báo lỗi hoạt động. [Giao diện xem đã quan sát](https://chophim.lat/xem/mot-thoi-ta-da-yeu#tap=episode-1&sv=Vietsub+%231&channel=0&server_id=0).

Card **Đúng là một cô gái ngoan ngoãn** cũng có nhãn Sắp chiếu. Quan sát card không chứng minh phim có trailer hoặc bản đầy đủ phát được. [Trang phim tương ứng](https://chophim.lat/phim/dung-la-mot-co-gai-ngoan-ngoan).

### Tương tác, hỗ trợ và quảng cáo

Trang chủ có Bình luận mới, các khối sôi nổi/yêu thích/xếp hạng thể loại và lời mời đăng nhập để lưu tiến độ, danh sách riêng. Chưa xác minh thuật toán, số liệu hoặc luồng riêng tư. [Trang chủ](https://chophim.lat/).

Đã gặp nhiều lớp thông báo/quảng cáo che thao tác. Có thao tác cố đóng thông báo và thao tác menu Quốc gia dẫn ra `fabet.clothing`; phiên duyệt quay lại ngay. Đóng một banner bằng phím Enter sau đó loại bỏ được banner. Trong trạng thái đã kiểm tra, thao tác với nút Thành viên, Gallery và bộ lọc chưa cho thấy panel mong đợi. Những thao tác này được ghi **chưa xác minh**, không kết luận mọi nút đều hỏng hoặc website không an toàn. Lumière nên giữ các hành động chính rõ ràng, không bị lớp quảng cáo ngoài cản trở. [Trang chủ](https://chophim.lat/), [trang phim đã kiểm tra](https://chophim.lat/phim/mot-thoi-ta-da-yeu), [danh mục chiếu rạp](https://chophim.lat/phim-chieu-rap).

Footer có các đích nội bộ riêng cho hỏi đáp, quyền riêng tư, điều khoản, giới thiệu và liên hệ. Đã xác nhận liên kết xuất hiện; chưa đánh giá đầy đủ nội dung, hiệu lực hoặc chức năng gửi liên hệ. [Quyền riêng tư](https://chophim.lat/chinh-sach-bao-mat), [điều khoản](https://chophim.lat/dieu-khoan-su-dung), [giới thiệu](https://chophim.lat/gioi-thieu), [liên hệ](https://chophim.lat/lien-he).

Đã mở trang Hỏi đáp thực tế: có **20 câu**, nhóm Tổng quan, Tài khoản, Xem phim, Tính năng và Hỗ trợ. Đưa focus vào câu **“Tôi có thể tạo nhiều danh sách phim không?”** rồi nhấn Enter mở được phần trả lời. Nội dung trả lời tự mô tả có danh sách tùy chỉnh ngoài danh sách yêu thích. Điều đã xác nhận là accordion và nội dung FAQ; chưa đăng nhập tạo danh sách nên chưa xác nhận tính năng phía sau. [Hỏi đáp Chợ Phim](https://chophim.lat/hoi-dap).

## Đối chiếu với Lumière

Phần Lumière bên dưới dựa trên mã nguồn hiện có trong đợt công việc này. Việc có triển khai không thay thế kiểm thử trình duyệt, tích hợp thanh toán hoặc vận hành thực tế.

| Nhu cầu | Lumière hiện có | Việc nên làm tiếp |
|---|---|---|
| Khám phá thư viện | Welcome và Browse, dropdown thể loại/quốc gia, diễn viên, tìm có dấu/không dấu và theo diễn viên, lọc năm/kết hợp | Thêm bộ sưu tập do quản trị biên tập; đo tìm kiếm rỗng và cải thiện dữ liệu |
| Thông tin để chọn phim | Năm, quốc gia, thể loại, mô tả, phim liên quan và xem nhanh | Bổ sung tên gốc, đạo diễn, phân loại độ tuổi/ngôn ngữ khi có nguồn; không tạo điểm TMDb hoặc badge chất lượng giả |
| Tình trạng sẵn sàng | Xác định bản xem từ tập đã xử lý xong; có trạng thái Đang chuẩn bị | Giữ CTA đúng trạng thái; không đánh đồng thiếu file với phim chưa phát hành |
| Trailer và điện ảnh | Đợt này đã có nguồn YouTube hoặc MP4 công khai, cùng cờ Phim chiếu rạp độc lập | Bổ sung trailer có quyền sử dụng, ghi nguồn và kiểm tra hiển thị từ card đến chi tiết |
| Tủ phim và thành viên | Lưu phim/tiến độ, hồ sơ/avatar, dashboard VIP và gia hạn, giao diện sáng/tối | Kiểm tra hành vi trên nhiều phiên; tránh mời mua lại như người chưa có VIP |
| Danh sách cá nhân do người dùng đặt tên | Có tủ phim để lưu, chưa có nhiều danh sách tùy đặt tên | Tùy chọn ưu tiên thấp khi người dùng cần tổ chức nhiều bộ sưu tập; FAQ Chợ Phim có mô tả nhưng chưa thử luồng tạo danh sách |
| Cộng đồng | Điểm đánh giá, bình luận, báo lỗi, phòng xem chung | Cân nhắc trả lời bình luận/ẩn spoiler; chỉ xếp hạng thịnh hành khi có dữ liệu thật |
| Video | Upload riêng tư, HLS và ticket theo phiên | Phụ đề, nhiều mức chất lượng hoặc track âm thanh cần pipeline thật, không chỉ thêm nhãn song ngữ |
| Hỗ trợ | FAQ tại Welcome/VIP, logic VNPay | Viết các trang hỗ trợ chung và thông tin thanh toán rõ ràng; kiểm thử VNPay tích hợp trước khi thu tiền |

Những điểm tham khảo trên đến từ giao diện [Chợ Phim](https://chophim.lat/), [chủ đề](https://chophim.lat/chu-de) và [trang chi tiết đã kiểm tra](https://chophim.lat/phim/mot-thoi-ta-da-yeu). Không có bằng chứng để kết luận Chợ Phim hoạt động tốt hơn Lumière ở mọi tính năng hoặc các luồng riêng tư tương đương.

## Quy ước trailer và nhãn cho Lumière

Ba thông tin cần độc lập:

| Thông tin | Ý nghĩa và nguồn |
|---|---|
| Có bản xem / Đang chuẩn bị | Có tập với `status=ready`; trailer không làm phim trở thành sẵn sàng |
| Phim chiếu rạp | Cờ `is_cinema_release` do quản trị biên tập; không khẳng định hiện còn chiếu tại rạp |
| Có trailer | Nguồn trailer riêng hợp lệ: YouTube hoặc MP4; không dùng URL bản phim đầy đủ |

“Chưa upload” không đồng nghĩa “Sắp chiếu”. Chỉ nên ghi “Sắp chiếu” hoặc “Đang chiếu rạp” khi có dữ liệu phát hành đáng tin cậy; hiện trạng thư viện có thể ghi trung thực là **Đang chuẩn bị**.

- Chưa có bản xem, có trailer: hành động chính là **Xem trailer**; không tạo link xem bản đầy đủ.
- Có bản xem và trailer: **Xem phim** theo quyền của người xem; trailer là lựa chọn riêng.
- Không có trailer: ẩn nút/player trailer rỗng.
- Trailer là nội dung giới thiệu công khai, kể cả khi bản đầy đủ thuộc VIP; không cấp ticket bản đầy đủ, VIP hoặc tiến độ xem phim.
- Phim nháp không xuất hiện qua danh mục hoặc đường dẫn trailer công khai.
- Quản trị chọn một nguồn trailer, kiểm tra file/URL và ghi nguồn khi cần; không dán HTML iframe tùy ý. Bản phim đầy đủ vẫn đi qua kho riêng tư và xử lý HLS.

## Kết quả các ca khảo sát Chợ Phim

| Ca | Kết quả và giới hạn |
|---|---|
| Mở trang chủ | Đã tải live trong trình duyệt |
| Tìm “Mùi Phở” rồi Enter | Sau khi dữ liệu tải xong có một kết quả đúng đường dẫn phim |
| Mở danh mục sắp chiếu | Quan sát 16 card trang 1/2, trộn nhãn Sắp chiếu và Full |
| Mở danh mục Phim Chiếu Rạp | Quan sát 16 card, trang 1/40, nhãn Full và phiên bản PĐ/TM/LT; chưa phát video |
| Mở chi tiết Một thời ta đã yêu | Quan sát metadata, trạng thái Trailer/Sắp chiếu và các mục nội dung |
| Từ Các bản chiếu chọn Xem bản này | Giao diện tải xong ghi Sắp chiếu: Trailer, Phần 1/Trailer; chưa nhấn phát hoặc xác nhận video hoạt động |
| Đóng thông báo/quảng cáo, mở menu Quốc gia | Có thao tác đi ra domain ngoài; đóng bằng Enter sau đó loại bỏ được banner |
| Mở Hỏi đáp, dùng Enter tại câu nhiều danh sách | Quan sát 20 câu và mở được câu trả lời; chưa thử tạo danh sách |
| Thành viên, Gallery, bộ lọc | Chưa xác minh panel/hành vi mong đợi trong trạng thái đã kiểm tra |
| Trailer, phụ đề, chất lượng, toàn bộ tập | Chưa kiểm chứng phát video |
| Đăng nhập, VIP, thư viện, xem chung, thanh toán | Chưa kiểm chứng luồng riêng tư |

## Ca nghiệm thu cần giữ cho Lumière

Đây là yêu cầu nghiệm thu, không phải tuyên bố mọi ca đã chạy thành công:

1. Chưa có tập ready nhưng có trailer: hiện Đang chuẩn bị và Xem trailer, không mở bản đầy đủ.
2. Chưa có tập ready và không trailer: không hiện player hoặc CTA rỗng.
3. Có tập ready và trailer: quyền xem bản đầy đủ vẫn đúng; trailer hoạt động độc lập.
4. Phim chiếu rạp có hoặc chưa có bản xem: nhãn điện ảnh không ghi đè trạng thái sẵn sàng.
5. Khách xem trailer phim VIP: không nhận quyền VIP, ticket hoặc lịch sử bản đầy đủ.
6. Phim nháp có trailer: không lộ từ Browse, quickview hoặc URL công khai.
7. URL ngoài danh sách cho phép, JavaScript/data URL và HTML iframe bị từ chối; CSP không được mở rộng tùy ý.
8. Upload giả đuôi MP4, codec/thời lượng/kích thước không hợp lệ bị từ chối; chỉ chọn một nguồn trailer.
9. Bộ lọc, tìm kiếm và phân trang giữ đúng trạng thái, nhãn và điều kiện đã chọn.
10. Sáng/tối và màn hình nhỏ đọc được; điều khiển bằng bàn phím được; đóng trailer không để âm thanh tiếp tục phát.

Trong đợt kiểm tra **05–06/11/2026**, lệnh `manage.py test cinema cinema.audit_experience_cases` chạy toàn bộ **196 ca, đều đạt**, trong **76,496 giây**. Kết quả tự động này không chứng minh các luồng chưa thử tại Chợ Phim hoặc khả năng phát của một video YouTube bên ngoài.

## Thứ tự cải thiện đề xuất

1. Hoàn thiện trailer, nhãn độc lập và dữ liệu thật; kiểm thử từ danh mục đến trang chi tiết, trailer và quyền xem phim.
2. Làm giàu metadata và tuyển tập theo chủ đề, ảnh diễn viên; ưu tiên nội dung có nguồn thay vì thêm nhiều khối rỗng.
3. Hoàn thiện nội dung hỏi đáp/liên hệ/điều khoản/quyền riêng tư; giữ hành động chính không bị popup che.
4. Phụ đề, mức chất lượng và ngôn ngữ chỉ bổ sung cùng khả năng xử lý/phát thực tế. Lịch chiếu, theo dõi và thông báo cần dữ liệu ngày/tập đáng tin cậy.
5. Kiểm thử VNPay tích hợp, xem chung bằng hai phiên, phục hồi tiến độ và tải đồng thời trước khi tuyên bố sẵn sàng phục vụ công khai.

Danh sách do người dùng đặt tên là cải tiến tùy chọn với ưu tiên thấp hơn các mục trên. Chỉ thêm khi có nhu cầu tổ chức thư viện rõ ràng, thay vì coi nội dung mô tả trong FAQ của website tham khảo là tính năng đã được kiểm chứng.

Các luồng chưa kiểm chứng ở Chợ Phim được để mở cho khảo sát tiếp theo; không suy ra thành công hay lỗi chỉ từ sự hiện diện của một nút.
