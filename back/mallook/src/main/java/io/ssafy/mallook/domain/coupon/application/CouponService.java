package io.ssafy.mallook.domain.coupon.application;

import io.ssafy.mallook.domain.coupon.dto.response.CouponRes;
import org.springframework.data.domain.Pageable;

import java.util.List;
import java.util.UUID;

public interface CouponService {
    List<CouponRes> findMyCouponList(Pageable pageable, UUID memberId);
}